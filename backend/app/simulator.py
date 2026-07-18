"""Software sensor-node simulator.

Stands in for the real field layer (ESP32 + probes + MQTT): every tick it
produces one reading per parameter per site, writes it through the same
ingestion path a real MQTT subscriber would use, and lets the rule engine
evaluate it. From the backend's point of view a simulated reading is
indistinguishable from a hardware one — which is the point: the entire
pipeline (sense -> store -> evaluate -> alert -> notify) runs for real.

Realism model:
  - Each (site, parameter) has a slowly wandering baseline near the middle
    of its crop band plus gaussian noise, so charts look organic.
  - Air temperature and light follow a day curve (Far North afternoons are
    the documented danger window in the SRS problem statement).
  - Occasionally a channel enters a "drift episode": the value walks out of
    band for a few ticks, which is exactly what makes Watch -> Alert fire
    during a demo.

Alert-coupled physics (what makes acknowledgement matter):
  - While a channel has an alert in Alert Raised / Notification Sent, the
    value SUSTAINS out of band. A real problem does not fix itself while
    everyone ignores the alert — pre-acknowledgement auto-recovery would
    make the whole notification chain pointless in the demo.
  - Once the alert is Acknowledged, the channel enters a RECOVERY ramp:
    the value eases back toward the middle of the band over several ticks,
    modelling the operator's corrective action taking effect. When it
    re-enters the band, the rule engine flips the alert to Resolved
    (correctiveActionVerified) — so the fix the dashboard animates is the
    fix that is actually happening in the data.
  - Modes are derived from the alert table every tick, not from in-memory
    flags, so a backend restart mid-alert resumes the right behaviour.

Also runs the timeoutExpired sweep: alerts stuck in Notification Sent past
the acknowledgement window take the shortcut to Closed (state machine's
right-side edge).
"""

import asyncio
import math
import random
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import audit, rule_engine
from .config import settings
from .database import session_scope
from .models import Alert, AlertState, Parameter, Reading, Site, utcnow
from .state_machine import transition

# Per-parameter noise scale (in parameter units) — roughly the sensor
# accuracy figures from SRS 3.2.
NOISE = {
    Parameter.ph: 0.05,
    Parameter.ec: 15.0,
    Parameter.water_temp: 0.2,
    Parameter.air_temp: 0.3,
    Parameter.humidity: 1.5,
    Parameter.water_level: 0.4,
    Parameter.light: 800.0,
}

# How far past the band edge a drift episode pushes, as a fraction of band width.
DRIFT_OVERSHOOT = 0.35

# Sustain mode: how fast the value settles onto its held out-of-band level.
SUSTAIN_EASE = 0.5

# Recovery mode: fraction of the distance back to band-centre covered per
# tick after acknowledgement. 0.25 ≈ visibly back in band within 4-6 ticks
# (under a minute at the default cadence) — long enough to watch, short
# enough for a live demo.
RECOVERY_PULL = 0.25


class ChannelSim:
    """Value generator for one (site, parameter) channel."""

    def __init__(self, band_min: float, band_max: float, param: Parameter):
        self.param = param
        self.band_min = band_min
        self.band_max = band_max
        mid = (band_min + band_max) / 2
        width = band_max - band_min
        self.baseline = random.uniform(mid - width * 0.15, mid + width * 0.15)
        self.drift_ticks_left = 0
        self.drift_direction = 1
        self.settle_ticks_left = 0

    def _finish(self, value: float) -> float:
        # Physical floors: no negative lux, level, EC, humidity or pH.
        if self.param is not Parameter.water_temp and self.param is not Parameter.air_temp:
            value = max(value, 0.0)
        return round(value, 2)

    def sustain_value(self, direction: int) -> float:
        """Hold the value out of band (unacknowledged raised alert). The
        baseline eases onto a level past the band edge and sits there."""
        width = self.band_max - self.band_min
        edge = self.band_max if direction > 0 else self.band_min
        target = edge + direction * width * DRIFT_OVERSHOOT
        self.drift_ticks_left = 0
        self.baseline += (target - self.baseline) * SUSTAIN_EASE
        return self._finish(self.baseline + random.gauss(0, NOISE[self.param]))

    def recover_value(self) -> float:
        """Ramp back toward band centre (acknowledged alert: the operator's
        corrective action is taking effect)."""
        mid = (self.band_min + self.band_max) / 2
        self.drift_ticks_left = 0
        # The alert resolves on the FIRST in-band reading, which happens
        # while the baseline is still near the band edge. Without a settling
        # tail, normal mode's seasonal swing (up to ±0.35×width for light)
        # would immediately push the channel back out and re-raise the alert
        # it just resolved — observed live before this existed.
        self.settle_ticks_left = 6
        self.baseline += (mid - self.baseline) * RECOVERY_PULL
        return self._finish(self.baseline + random.gauss(0, NOISE[self.param]))

    def next_value(self, tick: int) -> float:
        # Post-recovery settling: keep easing to band centre with seasonal
        # and drift suppressed, so the hand-back to normal mode starts from
        # the middle of the band instead of the edge it recovered across.
        if self.settle_ticks_left > 0:
            self.settle_ticks_left -= 1
            mid = (self.band_min + self.band_max) / 2
            self.baseline += (mid - self.baseline) * RECOVERY_PULL
            return self._finish(self.baseline + random.gauss(0, NOISE[self.param]))

        width = self.band_max - self.band_min

        # Day curve for the outdoor-ish parameters. One simulated "day" is
        # compressed into 180 ticks so a demo session sees rise and fall.
        day_phase = math.sin(2 * math.pi * (tick % 180) / 180)
        seasonal = 0.0
        if self.param is Parameter.air_temp:
            seasonal = day_phase * width * 0.25
        elif self.param is Parameter.light:
            seasonal = day_phase * width * 0.35
        elif self.param is Parameter.humidity:
            seasonal = -day_phase * width * 0.2  # dry afternoons

        # Maybe start a drift episode.
        if self.drift_ticks_left == 0 and random.random() < settings.SIM_DRIFT_PROBABILITY:
            self.drift_ticks_left = settings.SIM_DRIFT_DURATION_TICKS
            self.drift_direction = random.choice([-1, 1])

        drift = 0.0
        if self.drift_ticks_left > 0:
            # Push past the band edge; strongest mid-episode.
            progress = 1 - abs(self.drift_ticks_left - settings.SIM_DRIFT_DURATION_TICKS / 2) / (
                settings.SIM_DRIFT_DURATION_TICKS / 2
            )
            edge = self.band_max if self.drift_direction > 0 else self.band_min
            target = edge + self.drift_direction * width * DRIFT_OVERSHOOT
            drift = (target - self.baseline) * max(progress, 0.55)
            self.drift_ticks_left -= 1

        # The baseline itself wanders a little.
        self.baseline += random.gauss(0, NOISE[self.param] * 0.2)
        mid = (self.band_min + self.band_max) / 2
        self.baseline += (mid - self.baseline) * 0.02  # gentle pull back to centre

        value = self.baseline + seasonal + drift + random.gauss(0, NOISE[self.param])
        return self._finish(value)


class Simulator:
    def __init__(self):
        self.channels: dict[tuple[str, str], ChannelSim] = {}
        self.tick = 0
        self._task: asyncio.Task | None = None

    def _ensure_channels(self, db: Session, sites: list[Site]) -> None:
        for site in sites:
            for param in Parameter:
                key = (site.id, param.value)
                if key not in self.channels:
                    lo, hi = site.crop_profile.band(param)
                    self.channels[key] = ChannelSim(lo, hi, param)

    def _alert_modes(self, db: Session) -> dict[tuple[str, str], tuple[str, int]]:
        """Map (site_id, parameter) -> ("sustain"|"recover", direction).
        Derived from the alert table so behaviour survives restarts:
        raised-but-unacknowledged alerts sustain, acknowledged ones recover."""
        rows = db.scalars(
            select(Alert).where(Alert.state.in_((
                AlertState.alert_raised,
                AlertState.notification_sent,
                AlertState.acknowledged,
            )))
        ).all()
        modes: dict[tuple[str, str], tuple[str, int]] = {}
        for a in rows:
            direction = 1 if a.trigger_value > a.band_max else -1
            mode = "recover" if a.state is AlertState.acknowledged else "sustain"
            modes[(a.site_id, a.parameter.value)] = (mode, direction)
        return modes

    def step(self, db: Session) -> int:
        """One simulation tick: emit readings for every site, run the rule
        engine, sweep acknowledgement timeouts. Returns readings written."""
        sites = db.scalars(
            select(Site).options(
                selectinload(Site.crop_profile),
                selectinload(Site.sensor_node),
                selectinload(Site.operators),
            )
        ).all()
        self._ensure_channels(db, sites)
        alert_modes = self._alert_modes(db)
        written = 0

        for site in sites:
            node = site.sensor_node
            if node is None:
                continue
            node.last_seen = utcnow()
            for param in Parameter:
                sim = self.channels[(site.id, param.value)]
                mode = alert_modes.get((site.id, param.value))
                if mode is None:
                    value = sim.next_value(self.tick)
                elif mode[0] == "recover":
                    value = sim.recover_value()
                else:
                    value = sim.sustain_value(mode[1])
                reading = Reading(
                    site_id=site.id, node_id=node.id, parameter=param, value=value
                )
                db.add(reading)
                # FR 8.1 wants every reading in the audit trail.
                audit.log(db, "system", "reading",
                          f"{param.value}={value:g}", site.id)
                rule_engine.evaluate(db, reading, site)
                written += 1

        self._sweep_ack_timeouts(db)
        self.tick += 1
        return written

    def _sweep_ack_timeouts(self, db: Session) -> None:
        """timeoutExpired: Notification Sent -> Closed when nobody responds
        within the configured window, so alerts don't sit open forever."""
        deadline = utcnow() - timedelta(seconds=settings.ALERT_ACK_TIMEOUT_SECONDS)
        stale = db.scalars(
            select(Alert).where(
                Alert.state == AlertState.notification_sent,
                Alert.notified_at < deadline,
            )
        ).all()
        for alert in stale:
            transition(alert, AlertState.closed)
            alert.close_reason = "timeout_expired"
            audit.log(db, "system", "alert_timeout_closed",
                      f"{alert.parameter.value} alert unacknowledged for "
                      f"{settings.ALERT_ACK_TIMEOUT_SECONDS}s", alert.site_id)
            # Without an acknowledgement there is no recovery ramp; reset the
            # channel toward its band centre so a timed-out alert doesn't
            # immediately re-raise in an endless unattended loop.
            channel = self.channels.get((alert.site_id, alert.parameter.value))
            if channel:
                channel.baseline = (channel.band_min + channel.band_max) / 2
                channel.drift_ticks_left = 0
        if stale:
            # Same invariant as rule_engine: sessions run autoflush=False, so
            # make the closures visible to the next tick's queries even when
            # several ticks share one transaction (as the test suite does).
            db.flush()

    async def run(self):
        while True:
            db = session_scope()
            try:
                self.step(db)
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
            await asyncio.sleep(settings.SIM_INTERVAL_SECONDS)

    def start(self):
        self._task = asyncio.create_task(self.run())

    def stop(self):
        if self._task:
            self._task.cancel()


simulator = Simulator()

"""White-box unit tests for the simulator: reading emission, node
heartbeats, forced drift behaviour, and the timeoutExpired sweep."""

import random
from datetime import timedelta

import pytest

from app.config import settings
from app.models import (
    Alert,
    AlertState,
    AuditLog,
    Parameter,
    Reading,
    SensorNode,
    Site,
    SiteType,
    utcnow,
)
from app.simulator import ChannelSim, Simulator
from tests.conftest import get_site, make_alert


@pytest.fixture(autouse=True)
def deterministic():
    random.seed(42)


def test_step_emits_one_reading_per_site_per_parameter(seeded_db):
    sim = Simulator()
    written = sim.step(seeded_db)
    seeded_db.commit()
    assert written == 5 * len(Parameter)
    assert seeded_db.query(Reading).count() == 35


def test_step_stamps_node_heartbeat(seeded_db):
    sim = Simulator()
    sim.step(seeded_db)
    seeded_db.commit()
    for node in seeded_db.query(SensorNode).all():
        assert node.last_seen is not None


def test_every_reading_is_audited(seeded_db):
    """FR 8.1: the audit trail records every reading."""
    sim = Simulator()
    written = sim.step(seeded_db)
    seeded_db.commit()
    assert seeded_db.query(AuditLog).filter_by(action="reading").count() == written


def test_calm_channels_stay_in_band(seeded_db, monkeypatch):
    """With drift disabled, no reading should escape its band and no
    alerts should appear over many ticks."""
    monkeypatch.setattr(settings, "SIM_DRIFT_PROBABILITY", 0.0)
    sim = Simulator()
    for _ in range(10):
        sim.step(seeded_db)
    seeded_db.commit()
    assert seeded_db.query(Alert).count() == 0


def test_forced_drift_produces_alerts(seeded_db, monkeypatch):
    """With drift certain, the two-reading escalation must fire: after a
    few ticks there are alerts, and they went through Watch first."""
    monkeypatch.setattr(settings, "SIM_DRIFT_PROBABILITY", 1.0)
    sim = Simulator()
    for _ in range(6):
        sim.step(seeded_db)
    seeded_db.commit()
    alerts = seeded_db.query(Alert).all()
    assert alerts, "certain drift over 6 ticks must raise at least one alert"
    assert any(a.state == AlertState.notification_sent for a in alerts)
    # Escalated alerts must carry the Watch->Raised history stamps.
    for a in alerts:
        if a.state == AlertState.notification_sent:
            assert a.raised_at is not None and a.notified_at is not None


def test_channelsim_respects_physical_floors():
    """EC, humidity, light, level and pH can never go negative even if a
    downward drift plus noise tries to push them there."""
    sim = ChannelSim(0.5, 2.0, Parameter.ec)
    sim.baseline = -50  # force a pathological internal state
    for tick in range(50):
        assert sim.next_value(tick) >= 0.0


def test_timeout_sweep_closes_stale_notification_sent(seeded_db):
    """timeoutExpired: Notification Sent past the ack window -> Closed."""
    site = get_site(seeded_db, "GSS Maroua")
    stale = make_alert(seeded_db, site)
    stale.notified_at = utcnow() - timedelta(seconds=settings.ALERT_ACK_TIMEOUT_SECONDS + 60)
    fresh = make_alert(seeded_db, site, parameter=Parameter.ec, trigger_value=2500)
    seeded_db.commit()

    Simulator()._sweep_ack_timeouts(seeded_db)
    seeded_db.commit()

    seeded_db.refresh(stale)
    seeded_db.refresh(fresh)
    assert stale.state is AlertState.closed
    assert stale.close_reason == "timeout_expired"
    assert fresh.state is AlertState.notification_sent  # inside the window


def test_timeout_sweep_ignores_acknowledged(seeded_db):
    """Only un-acknowledged alerts time out; an acknowledged one waits for
    resolution however long that takes."""
    site = get_site(seeded_db, "GSS Maroua")
    acked = make_alert(seeded_db, site, state=AlertState.acknowledged)
    acked.notified_at = utcnow() - timedelta(days=2)
    seeded_db.commit()
    Simulator()._sweep_ack_timeouts(seeded_db)
    seeded_db.commit()
    seeded_db.refresh(acked)
    assert acked.state is AlertState.acknowledged


def test_raised_alert_sustains_out_of_band(seeded_db, monkeypatch):
    """A problem nobody acknowledged must not fix itself: while an alert is
    in Notification Sent, the channel keeps reading out of band."""
    monkeypatch.setattr(settings, "SIM_DRIFT_PROBABILITY", 0.0)
    site = get_site(seeded_db, "GSS Maroua")
    make_alert(seeded_db, site, parameter=Parameter.humidity, trigger_value=30.0)  # band 50-80

    sim = Simulator()
    for _ in range(10):
        sim.step(seeded_db)
    seeded_db.commit()

    lo, hi = site.crop_profile.band(Parameter.humidity)
    readings = seeded_db.query(Reading).filter_by(
        site_id=site.id, parameter=Parameter.humidity).all()
    out_of_band = [r for r in readings if not lo <= r.value <= hi]
    # The first tick or two may still be easing onto the sustain level;
    # after that every reading must be out of band on the low side.
    assert len(out_of_band) >= 8
    assert all(r.value < lo for r in out_of_band)
    seeded_db.expire_all()
    alert = seeded_db.query(Alert).filter_by(parameter=Parameter.humidity).one()
    assert alert.state is AlertState.notification_sent


def test_acknowledged_alert_recovers_and_resolves(seeded_db, monkeypatch):
    """Acknowledgement starts the recovery ramp; the value re-enters the
    band within a handful of ticks and the rule engine then flips the
    alert to Resolved (correctiveActionVerified) — no manual nudge."""
    monkeypatch.setattr(settings, "SIM_DRIFT_PROBABILITY", 0.0)
    site = get_site(seeded_db, "GSS Maroua")
    alert = make_alert(seeded_db, site, parameter=Parameter.humidity,
                       state=AlertState.acknowledged, trigger_value=30.0)

    sim = Simulator()
    # Start the channel where the sustained problem left it: far out of band.
    sim._ensure_channels(seeded_db, [site])
    sim.channels[(site.id, Parameter.humidity.value)].baseline = 30.0

    for ticks in range(1, 16):
        sim.step(seeded_db)
        seeded_db.commit()
        seeded_db.expire_all()
        if seeded_db.get(Alert, alert.id).state is AlertState.resolved:
            break
    assert seeded_db.get(Alert, alert.id).state is AlertState.resolved, \
        "recovery ramp should re-enter the band and resolve within 15 ticks"
    # And it stays healthy afterwards: no new alert on that channel.
    for _ in range(3):
        sim.step(seeded_db)
    seeded_db.commit()
    open_states = (AlertState.watch, AlertState.alert_raised,
                   AlertState.notification_sent, AlertState.acknowledged)
    assert seeded_db.query(Alert).filter(
        Alert.parameter == Parameter.humidity,
        Alert.state.in_(open_states)).count() == 0


def test_timeout_reset_prevents_realert_loop(seeded_db, monkeypatch):
    """After timeoutExpired closes an unacknowledged alert, the channel is
    reset toward band centre instead of sustaining forever and re-raising."""
    monkeypatch.setattr(settings, "SIM_DRIFT_PROBABILITY", 0.0)
    site = get_site(seeded_db, "GSS Maroua")
    stale = make_alert(seeded_db, site, parameter=Parameter.humidity, trigger_value=30.0)
    stale.notified_at = utcnow() - timedelta(seconds=settings.ALERT_ACK_TIMEOUT_SECONDS + 60)
    seeded_db.commit()

    sim = Simulator()
    for _ in range(4):
        sim.step(seeded_db)
    seeded_db.commit()
    seeded_db.expire_all()
    assert seeded_db.get(Alert, stale.id).state is AlertState.closed
    last = (seeded_db.query(Reading)
            .filter_by(site_id=site.id, parameter=Parameter.humidity)
            .order_by(Reading.ts.desc()).first())
    lo, hi = site.crop_profile.band(Parameter.humidity)
    assert lo <= last.value <= hi


def test_prune_drops_old_readings_and_reading_audit(seeded_db, monkeypatch):
    """Retention keeps the readings table small: rows older than the window
    are pruned, along with their per-reading audit entries, while recent
    data and non-reading audit entries are kept."""
    from app.models import AuditLog
    from datetime import timedelta

    monkeypatch.setattr(settings, "RETENTION_HOURS", 12)
    site = get_site(seeded_db, "GSS Maroua")
    node = site.sensor_node
    old = utcnow() - timedelta(hours=20)
    recent = utcnow() - timedelta(hours=1)

    seeded_db.add(Reading(site_id=site.id, node_id=node.id,
                          parameter=Parameter.ph, value=6.0, ts=old))
    seeded_db.add(Reading(site_id=site.id, node_id=node.id,
                          parameter=Parameter.ph, value=6.1, ts=recent))
    seeded_db.add(AuditLog(actor="system", action="reading", detail="ph=6", ts=old))
    seeded_db.add(AuditLog(actor="admin", action="alert_acknowledged",
                           detail="kept", ts=old))
    seeded_db.commit()

    Simulator()._prune_old_data(seeded_db)
    seeded_db.commit()

    values = [r.value for r in seeded_db.query(Reading).all()]
    assert 6.1 in values and 6.0 not in values  # old reading gone, recent kept
    actions = [a.action for a in seeded_db.query(AuditLog).all()]
    assert "reading" not in actions            # old reading-audit pruned
    assert "alert_acknowledged" in actions     # action audit kept regardless


def test_run_survives_a_failing_tick(SessionFactory, seeded_db, monkeypatch):
    """A single failing tick must not kill the feed. This is the Render bug:
    managed Postgres drops idle connections, a commit fails, and the old
    loop re-raised and stopped forever — no more readings, no more alerts to
    acknowledge. The loop must log, roll back, and keep ticking."""
    import asyncio

    import app.simulator as sim_mod

    monkeypatch.setattr(sim_mod, "session_scope", lambda: SessionFactory())
    monkeypatch.setattr(settings, "SIM_INTERVAL_SECONDS", 0.01)

    sim = sim_mod.Simulator()
    real_step = sim.step
    calls = {"n": 0}

    def flaky_step(db):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient DB blip")
        return real_step(db)

    monkeypatch.setattr(sim, "step", flaky_step)

    async def drive():
        task = asyncio.create_task(sim.run())
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(drive())

    # Kept ticking after the first tick raised, and wrote data on good ticks.
    assert calls["n"] >= 3
    assert seeded_db.query(Reading).count() > 0


def test_new_site_gets_channels_on_next_tick(seeded_db):
    """Registering a site mid-run must not crash the simulator; it picks
    the site up on the next tick (as promised in API.md)."""
    sim = Simulator()
    sim.step(seeded_db)
    site = get_site(seeded_db, "GSS Maroua")
    new = Site(name="New Farm", site_type=SiteType.school, location="Mora",
               crop_profile=site.crop_profile)
    seeded_db.add(new)
    seeded_db.add(SensorNode(site=new))
    seeded_db.commit()
    written = sim.step(seeded_db)
    assert written == 6 * len(Parameter)

"""Rule engine (FR 4): compares each stored reading to the site's active
crop band and drives the alert state machine.

Escalation logic (SRS 'Key Design Decisions'):
  - 1st out-of-band reading on a channel  -> Watch (elevated monitoring,
    amber on the dashboard, no notification yet). This absorbs one-off
    sensor spikes so we don't page an operator for electrical noise on the
    pH probe.
  - 2nd consecutive out-of-band reading   -> Alert Raised, then immediately
    Notification Sent (the dispatcher runs synchronously right after, so
    the alert-latency budget in NFR 1.2 is bounded by one function call,
    not a queue hop).
  - A reading back inside the band while in Watch closes the Watch as a
    false alarm; while in Acknowledged it moves the alert to Resolved
    (correctiveActionVerified — 'the system checks readings are back to
    normal').

Why "consecutive" is per (site, parameter): each parameter is an
independent channel per the SRS ('a second out-of-band reading on the same
channel causes an Alert').
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import audit, notifier
from .models import Alert, AlertState, Reading, Site
from .state_machine import transition

# States in which an alert is still "live" for its (site, parameter) channel.
OPEN_STATES = (
    AlertState.watch,
    AlertState.alert_raised,
    AlertState.notification_sent,
    AlertState.acknowledged,
)


def _open_alert(db: Session, site_id: str, parameter) -> Alert | None:
    return db.scalar(
        select(Alert)
        .where(Alert.site_id == site_id,
               Alert.parameter == parameter,
               Alert.state.in_(OPEN_STATES))
        .order_by(Alert.created_at.desc())
        .limit(1)
    )


def evaluate(db: Session, reading: Reading, site: Site) -> Alert | None:
    """Run after every reading insert (SRS 2.1 step 8: 'immediately after a
    write'). Returns the alert it touched, if any. Caller commits."""
    band_min, band_max = site.crop_profile.band(reading.parameter)
    in_band = band_min <= reading.value <= band_max
    alert = _open_alert(db, site.id, reading.parameter)

    if in_band:
        if alert is None:
            return None  # Normal -> Normal: nothing to do.
        if alert.state is AlertState.watch:
            # Single spike, recovered on the next sample: dismiss quietly.
            transition(alert, AlertState.closed)
            alert.close_reason = "recovered_in_watch"
            audit.log(db, "system", "watch_recovered",
                      f"{reading.parameter.value} back in band at {reading.value:.2f}",
                      site.id)
        elif alert.state is AlertState.acknowledged:
            # Operator acted and the value came back: corrective action verified.
            transition(alert, AlertState.resolved)
            audit.log(db, "system", "alert_resolved",
                      f"{reading.parameter.value} back in band at {reading.value:.2f}",
                      site.id)
        # alert_raised / notification_sent: a lone in-band sample does NOT
        # silence an un-acknowledged alert. The operator still needs to see
        # and acknowledge it; resolution requires acknowledgement first per
        # the state machine (Notification Sent has no edge to Resolved).
        return alert

    # Out of band.
    if alert is None:
        alert = Alert(
            site_id=site.id,
            parameter=reading.parameter,
            state=AlertState.watch,
            trigger_value=reading.value,
            band_min=band_min,
            band_max=band_max,
        )
        db.add(alert)
        audit.log(db, "system", "watch_started",
                  f"{reading.parameter.value} out of band: {reading.value:.2f} "
                  f"(target {band_min:g}-{band_max:g})", site.id)
        return alert

    if alert.state is AlertState.watch:
        # Second consecutive out-of-band reading confirms it is not a spike.
        alert.trigger_value = reading.value
        transition(alert, AlertState.alert_raised)
        audit.log(db, "system", "alert_raised",
                  f"{reading.parameter.value} still out of band: {reading.value:.2f}",
                  site.id)
        notifier.dispatch(db, alert, site)
        transition(alert, AlertState.notification_sent)
        return alert

    # Already raised/notified/acknowledged and still out of band: keep the
    # existing alert open rather than stacking duplicates on the channel.
    return alert

"""Notification dispatcher (FR 5, activity diagram step 3).

The dashboard banner channel is implemented for real: a Notification row
with channel=dashboard is picked up by the frontend's poll loop and shown
as a live banner.

Email, SMS and USSD-push are stubbed: no SMTP/SMS/USSD provider exists in
this environment, so instead of sending we persist a Notification row with
status="simulated" containing the exact message that *would* have gone out
(SRS 3.1 formats). The admin panel renders these so the demo can show the
full multi-channel story without external accounts.
"""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import audit
from .config import settings
from .models import Alert, Channel, Notification, Site, User, utcnow

PARAM_LABELS = {
    "ph": {"en": "pH", "fr": "pH"},
    "ec": {"en": "EC", "fr": "CE"},
    "water_temp": {"en": "water temperature", "fr": "température de l'eau"},
    "air_temp": {"en": "air temperature", "fr": "température de l'air"},
    "humidity": {"en": "humidity", "fr": "humidité"},
    "water_level": {"en": "water level", "fr": "niveau d'eau"},
    "light": {"en": "light", "fr": "luminosité"},
}

PARAM_UNITS = {
    "ph": "", "ec": " µS/cm", "water_temp": " °C", "air_temp": " °C",
    "humidity": " %", "water_level": " cm", "light": " lux",
}


def _fmt(value: float) -> str:
    return f"{value:g}" if value == round(value, 1) else f"{value:.1f}"


def build_message(alert: Alert, site: Site, channel: Channel, lang: str) -> str:
    """One consistent alert text across all channels (SRS 3.1 'consistent
    terminology in alerts'), with the SMS variant kept under 160 chars."""
    p = alert.parameter.value
    label = PARAM_LABELS[p][lang]
    unit = PARAM_UNITS[p]
    val = _fmt(alert.trigger_value) + unit
    band = f"{_fmt(alert.band_min)}-{_fmt(alert.band_max)}{unit}"

    if channel is Channel.sms:
        # SRS 3.1 format, < 160 chars:
        # "VertiBottle ALERT: <site> pH 4.8 (target 5.5-6.5). Check now. Reply ACK..."
        if lang == "fr":
            return (f"VertiBottle ALERTE: {site.name} {label} {val} "
                    f"(cible {band}). Verifiez maintenant. Repondez ACK pour confirmer.")
        return (f"VertiBottle ALERT: {site.name} {label} {val} "
                f"(target {band}). Check now. Reply ACK to acknowledge.")

    if lang == "fr":
        return (f"Alerte {site.name} : {label} = {val}, hors de la plage cible {band}. "
                f"Une intervention est nécessaire.")
    return (f"Alert at {site.name}: {label} is {val}, outside the target band {band}. "
            f"Action is needed.")


def _under_daily_limit(db: Session, site_id: str, channel: Channel) -> bool:
    """SRS business rule: max 20 dispatches per channel per site per day."""
    since = utcnow() - timedelta(days=1)
    count = db.scalar(
        select(func.count(Notification.id)).where(
            Notification.site_id == site_id,
            Notification.channel == channel,
            Notification.sent_at >= since,
        )
    )
    return (count or 0) < settings.NOTIFICATION_DAILY_LIMIT


def dispatch(db: Session, alert: Alert, site: Site) -> list[Notification]:
    """Fan an alert out to every operator of the site on every channel that
    applies to them (activity diagram: fork into dashboard/email/SMS/USSD).
    Returns the created Notification rows; caller commits."""
    created: list[Notification] = []
    operators: list[User] = [u for u in site.operators if u.active]

    for op in operators:
        lang = op.language or "en"
        # Dashboard banner: always, for every operator (SRS 2.1 step 9).
        channels: list[tuple[Channel, str, str]] = [
            (Channel.dashboard, op.username, "delivered")
        ]
        if op.email:
            channels.append((Channel.email, op.email, "simulated"))
        if op.phone:
            channels.append((Channel.sms, op.phone, "simulated"))
            channels.append((Channel.ussd, op.phone, "simulated"))

        for channel, recipient, status in channels:
            if not _under_daily_limit(db, site.id, channel):
                audit.log(db, "system", "notification_rate_limited",
                          f"{channel.value} limit reached for site", site.id)
                continue
            note = Notification(
                alert_id=alert.id,
                site_id=site.id,
                channel=channel,
                recipient=recipient,
                message=build_message(alert, site, channel, lang),
                status=status,
            )
            db.add(note)
            created.append(note)
            audit.log(db, "system", "notification_dispatched",
                      f"{channel.value} to {recipient} for {alert.parameter.value} alert",
                      site.id)
    return created

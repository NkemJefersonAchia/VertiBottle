"""White-box unit tests for the notification dispatcher: message formats
(SRS 3.1), per-language rendering, channel fan-out and the daily rate limit
business rule."""

from app import notifier
from app.config import settings
from app.models import AlertState, AuditLog, Channel, Notification, Parameter
from tests.conftest import get_site, make_alert


def test_sms_format_matches_srs_and_length(seeded_db):
    """SRS 3.1: 'VertiBottle ALERT: <site> pH 4.8 (target 5.5-6.5). Check
    now. Reply ACK to acknowledge.' and under 160 characters."""
    site = get_site(seeded_db, "GSS Maroua")
    alert = make_alert(seeded_db, site, trigger_value=4.8)
    msg = notifier.build_message(alert, site, Channel.sms, "en")
    assert msg.startswith("VertiBottle ALERT: GSS Maroua Bottle Farm pH 4.8")
    assert "(target 5.5-6.5)" in msg
    assert "Reply ACK" in msg
    assert len(msg) < 160


def test_sms_french(seeded_db):
    site = get_site(seeded_db, "Makabay")
    alert = make_alert(seeded_db, site, parameter=Parameter.ec, trigger_value=2500)
    msg = notifier.build_message(alert, site, Channel.sms, "fr")
    assert msg.startswith("VertiBottle ALERTE:")
    assert "CE" in msg  # French label for EC
    assert len(msg) < 160


def test_dashboard_message_has_units_and_band(seeded_db):
    site = get_site(seeded_db, "GSS Maroua")
    alert = make_alert(seeded_db, site, parameter=Parameter.water_temp, trigger_value=31.0)
    msg = notifier.build_message(alert, site, Channel.dashboard, "en")
    assert "31 °C" in msg
    assert "18-26 °C" in msg


def test_dispatch_fans_out_per_operator_contacts(seeded_db):
    """GSS Maroua's operator (school_op) has phone + email, so one alert
    must produce dashboard + email + sms + ussd notifications."""
    site = get_site(seeded_db, "GSS Maroua")
    alert = make_alert(seeded_db, site, state=AlertState.alert_raised)
    created = notifier.dispatch(seeded_db, alert, site)
    seeded_db.commit()
    channels = {n.channel for n in created}
    assert channels == {Channel.dashboard, Channel.email, Channel.sms, Channel.ussd}
    # Banner is the real channel; the rest are explicitly simulated.
    statuses = {n.channel: n.status for n in created}
    assert statuses[Channel.dashboard] == "delivered"
    assert statuses[Channel.sms] == "simulated"


def test_dispatch_no_email_channel_for_operator_without_email(seeded_db):
    """cb_op (Makabay) has a phone but no email address."""
    site = get_site(seeded_db, "Makabay")
    alert = make_alert(seeded_db, site, state=AlertState.alert_raised)
    created = notifier.dispatch(seeded_db, alert, site)
    channels = {n.channel for n in created}
    assert Channel.email not in channels
    assert Channel.ussd in channels


def test_dispatch_uses_operator_language(seeded_db):
    site = get_site(seeded_db, "Makabay")  # cb_op is French
    alert = make_alert(seeded_db, site, state=AlertState.alert_raised)
    created = notifier.dispatch(seeded_db, alert, site)
    sms = next(n for n in created if n.channel == Channel.sms)
    assert "ALERTE" in sms.message


def test_daily_rate_limit_enforced_and_audited(seeded_db, monkeypatch):
    """Business rule: max N dispatches per channel per site per day. Once
    the cap is reached the send is skipped and the skip itself is logged."""
    monkeypatch.setattr(settings, "NOTIFICATION_DAILY_LIMIT", 1)
    site = get_site(seeded_db, "GSS Maroua")

    a1 = make_alert(seeded_db, site, state=AlertState.alert_raised)
    first = notifier.dispatch(seeded_db, a1, site)
    seeded_db.commit()
    assert len(first) == 4  # one per channel, cap not yet hit

    a2 = make_alert(seeded_db, site, state=AlertState.alert_raised,
                    parameter=Parameter.ec, trigger_value=2500)
    second = notifier.dispatch(seeded_db, a2, site)
    seeded_db.commit()
    assert second == []  # every channel at its cap

    skips = seeded_db.query(AuditLog).filter_by(action="notification_rate_limited").count()
    assert skips == 4


def test_rate_limit_is_per_site(seeded_db, monkeypatch):
    monkeypatch.setattr(settings, "NOTIFICATION_DAILY_LIMIT", 1)
    maroua = get_site(seeded_db, "GSS Maroua")
    salak = get_site(seeded_db, "Salak")
    notifier.dispatch(seeded_db, make_alert(seeded_db, maroua, state=AlertState.alert_raised), maroua)
    seeded_db.commit()
    # Maroua's cap must not affect Salak.
    created = notifier.dispatch(seeded_db, make_alert(seeded_db, salak, state=AlertState.alert_raised), salak)
    assert len(created) > 0


def test_inactive_operator_gets_nothing(seeded_db):
    site = get_site(seeded_db, "GSS Maroua")
    for op in site.operators:
        op.active = False
    seeded_db.commit()
    created = notifier.dispatch(seeded_db, make_alert(seeded_db, site, state=AlertState.alert_raised), site)
    assert created == []

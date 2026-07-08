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

"""Rule engine behaviour against an in-memory SQLite database: the
Watch-on-first / Alert-on-second escalation and the recovery paths."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import rule_engine
from app.models import (
    AlertState,
    Base,
    Channel,
    CropProfile,
    Parameter,
    Reading,
    Role,
    SensorNode,
    Site,
    SiteType,
    User,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def site(db):
    crop = CropProfile(
        crop_name="lettuce",
        ph_min=5.5, ph_max=6.5, ec_min=800, ec_max=1200,
        water_temp_min=18, water_temp_max=26, air_temp_min=15, air_temp_max=28,
        humidity_min=50, humidity_max=80, water_level_min=10, water_level_max=30,
        light_min=10000, light_max=40000,
    )
    s = Site(name="Test Farm", site_type=SiteType.school, location="Maroua",
             crop_profile=crop)
    node = SensorNode(site=s)
    op = User(username="op", password_hash="x", name="Op",
              role=Role.school_operator, site=s, email="op@x.example",
              phone="+237000", language="en", preferred_channel=Channel.email)
    db.add_all([crop, s, node, op])
    db.commit()
    return s


def reading(db, site, value, param=Parameter.ph):
    r = Reading(site_id=site.id, node_id=site.sensor_node.id, parameter=param, value=value)
    db.add(r)
    db.flush()
    return r


def test_in_band_reading_creates_nothing(db, site):
    assert rule_engine.evaluate(db, reading(db, site, 6.0), site) is None


def test_first_out_of_band_creates_watch(db, site):
    alert = rule_engine.evaluate(db, reading(db, site, 4.8), site)
    assert alert.state is AlertState.watch


def test_second_out_of_band_raises_and_notifies(db, site):
    rule_engine.evaluate(db, reading(db, site, 4.8), site)
    alert = rule_engine.evaluate(db, reading(db, site, 4.7), site)
    # Raised then immediately dispatched -> Notification Sent.
    assert alert.state is AlertState.notification_sent
    assert alert.notified_at is not None
    # Dashboard banner + email + SMS + USSD for an operator with all contacts.
    channels = {n.channel for n in alert.notifications}
    assert Channel.dashboard in channels
    assert Channel.email in channels


def test_spike_recovers_in_watch(db, site):
    rule_engine.evaluate(db, reading(db, site, 4.8), site)
    alert = rule_engine.evaluate(db, reading(db, site, 6.0), site)
    assert alert.state is AlertState.closed
    assert alert.close_reason == "recovered_in_watch"


def test_recovery_after_ack_resolves(db, site):
    from app.state_machine import transition

    rule_engine.evaluate(db, reading(db, site, 4.8), site)
    alert = rule_engine.evaluate(db, reading(db, site, 4.7), site)
    transition(alert, AlertState.acknowledged)
    alert = rule_engine.evaluate(db, reading(db, site, 6.0), site)
    assert alert.state is AlertState.resolved


def test_in_band_does_not_silence_unacknowledged_alert(db, site):
    rule_engine.evaluate(db, reading(db, site, 4.8), site)
    rule_engine.evaluate(db, reading(db, site, 4.7), site)
    alert = rule_engine.evaluate(db, reading(db, site, 6.0), site)
    # Still awaiting a human: recovery alone must not close a sent alert.
    assert alert.state is AlertState.notification_sent


def test_no_duplicate_alert_while_open(db, site):
    rule_engine.evaluate(db, reading(db, site, 4.8), site)
    a1 = rule_engine.evaluate(db, reading(db, site, 4.7), site)
    a2 = rule_engine.evaluate(db, reading(db, site, 4.6), site)
    assert a1.id == a2.id


def test_parameters_are_independent_channels(db, site):
    rule_engine.evaluate(db, reading(db, site, 4.8, Parameter.ph), site)
    alert = rule_engine.evaluate(db, reading(db, site, 3000, Parameter.ec), site)
    # EC's first excursion is its own Watch, not an escalation of pH's.
    assert alert.state is AlertState.watch
    assert alert.parameter is Parameter.ec

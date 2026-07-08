"""Shared fixtures.

The whole suite runs against in-memory SQLite (StaticPool so every session
and every TestClient thread sees the same database). The app's lifespan is
deliberately NOT run: TestClient without a context manager skips it, which
keeps the Postgres connection, the seeding-on-boot and the background
simulator out of the tests. Seeding is done explicitly per fixture instead,
so each test starts from a known state — the same 5 sites / 4 crops / 8
users a fresh install gets.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.main import app
from app.models import Alert, AlertState, Base, Parameter, Site, User, utcnow
from app.seed import seed


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def SessionFactory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def db(SessionFactory):
    session = SessionFactory()
    yield session
    session.close()


@pytest.fixture()
def seeded_db(db):
    seed(db)
    return db


@pytest.fixture()
def client(SessionFactory, seeded_db):
    """TestClient wired to the seeded SQLite database."""

    def override_get_db():
        session = SessionFactory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def login(client, username, password="demo1234"):
    res = client.post("/api/v1/auth/login",
                      json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_token(client):
    return login(client, "admin")


@pytest.fixture()
def coordinator_token(client):
    return login(client, "coordinator")


@pytest.fixture()
def school_op_token(client):
    return login(client, "school_op")


@pytest.fixture()
def agronomist_token(client):
    return login(client, "agronomist")


def get_site(db, name_fragment: str) -> Site:
    return next(s for s in db.query(Site).all() if name_fragment in s.name)


def get_user(db, username: str) -> User:
    return db.query(User).filter_by(username=username).one()


def make_alert(db, site: Site, state=AlertState.notification_sent,
               parameter=Parameter.ph, trigger_value=4.8) -> Alert:
    """Insert an alert directly in a given lifecycle state, with the
    timestamp columns a real alert would have accumulated on the way."""
    lo, hi = site.crop_profile.band(parameter)
    now = utcnow()
    alert = Alert(
        site_id=site.id, parameter=parameter, state=state,
        trigger_value=trigger_value, band_min=lo, band_max=hi,
    )
    if state in (AlertState.alert_raised, AlertState.notification_sent,
                 AlertState.acknowledged, AlertState.resolved, AlertState.closed):
        alert.raised_at = now
    if state in (AlertState.notification_sent, AlertState.acknowledged,
                 AlertState.resolved, AlertState.closed):
        alert.notified_at = now
    if state in (AlertState.acknowledged, AlertState.resolved, AlertState.closed):
        alert.acknowledged_at = now
    if state in (AlertState.resolved, AlertState.closed):
        alert.resolved_at = now
    if state is AlertState.closed:
        alert.closed_at = now
    db.add(alert)
    db.commit()
    return alert

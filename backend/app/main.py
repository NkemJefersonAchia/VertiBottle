"""VertiBottle backend entry point.

Startup sequence (one command, per the deliverable requirement):
  1. create tables if missing (Alembic owns real migrations; create_all
     makes the first run frictionless),
  2. try to enable TimescaleDB (falls back silently — see database.py),
  3. seed the 5 pilot sites / 4 crops / demo users if the DB is empty,
  4. start the sensor simulator so the dashboard has live data within
     seconds of launching.

The frontend is plain static files served straight from FastAPI, so the
whole app is a single process on one port.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .database import engine, session_scope, try_enable_timescale
from .models import Base
from .routers import admin, alerts, auth, notifications, readings, sites, ussd
from .seed import seed
from .simulator import simulator

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    app.state.timescale = try_enable_timescale()
    db = session_scope()
    try:
        seed(db)
    finally:
        db.close()
    simulator.start()
    yield
    simulator.stop()


app = FastAPI(
    title="VertiBottle API",
    version="1.0",
    description=(
        "Sensor-based monitoring for hydroponic bottle farms. "
        "REST surface for the dashboard, USSD simulator and admin console. "
        "See docs/API.md for the written guide."
    ),
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(sites.router)
app.include_router(readings.router)
app.include_router(alerts.router)
app.include_router(notifications.router)
app.include_router(ussd.router)
app.include_router(admin.router)


@app.get("/api/v1/status", tags=["meta"])
def status():
    """Liveness probe + whether the TimescaleDB fallback is in effect.
    (timescaledb is None if the lifespan hasn't run, e.g. under TestClient.)"""
    return {"ok": True, "timescaledb": getattr(app.state, "timescale", None)}


# Mounted last so /api/* wins routing; html=True serves index.html at /.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

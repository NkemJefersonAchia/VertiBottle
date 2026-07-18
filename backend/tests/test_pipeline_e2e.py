"""System-level test: the complete SRS pipeline in one scenario, driven
through the public API wherever a human would act.

sense -> ingest -> rule engine -> Watch -> Alert Raised -> Notification
Sent (all channels) -> operator acknowledges -> readings recover ->
Resolved -> coordinator closes -> audit trail tells the whole story.

Grey-box: the simulator's channel state is manipulated directly to force
the drift deterministically (a real farm's pH is not on the test's
schedule), but every observation and action goes through the HTTP API.
"""

import random

from app.config import settings
from app.models import Parameter
from app.simulator import Simulator
from tests.conftest import auth, get_site


def test_full_alert_lifecycle(client, school_op_token, coordinator_token,
                              admin_token, seeded_db, monkeypatch):
    # Determinism: no random drift episodes — the pH excursion below is the
    # only out-of-band event in this scenario.
    monkeypatch.setattr(settings, "SIM_DRIFT_PROBABILITY", 0.0)
    random.seed(7)
    sim = Simulator()
    sim.step(seeded_db)  # tick 1: healthy baseline everywhere
    seeded_db.commit()

    site = get_site(seeded_db, "GSS Maroua")
    hdr_op = auth(school_op_token)
    hdr_coord = auth(coordinator_token)

    # Force GSS Maroua's pH channel far out of band (below 5.5).
    ph_channel = sim.channels[(site.id, Parameter.ph.value)]
    ph_channel.baseline = 3.0

    # Tick 2: first out-of-band reading -> Watch (amber, no notification).
    sim.step(seeded_db)
    seeded_db.commit()
    alerts = client.get(f"/api/v1/alerts?site_id={site.id}&active=true", headers=hdr_op).json()
    ph_alerts = [a for a in alerts if a["parameter"] == "ph"]
    assert ph_alerts and ph_alerts[0]["state"] == "watch"
    assert client.get("/api/v1/notifications", headers=hdr_op).json() == []
    assert client.get(f"/api/v1/sites/{site.id}", headers=hdr_op).json()["status"] == "amber"

    # Tick 3: second consecutive out-of-band -> raised + dispatched.
    sim.step(seeded_db)
    seeded_db.commit()
    alert = [a for a in client.get(f"/api/v1/alerts?site_id={site.id}&active=true",
                                   headers=hdr_op).json()
             if a["parameter"] == "ph"][0]
    assert alert["state"] == "notification_sent"
    assert client.get(f"/api/v1/sites/{site.id}", headers=hdr_op).json()["status"] == "red"

    # The operator's dashboard banner arrived (the real channel)...
    banners = client.get("/api/v1/notifications", headers=hdr_op).json()
    assert any(b["alert_id"] == alert["id"] for b in banners)
    # ...and the simulated channels logged their would-have-sent content.
    outbox = client.get("/api/v1/notifications/outbox", headers=auth(admin_token)).json()
    channels = {n["channel"] for n in outbox if n["alert_id"] == alert["id"]}
    assert channels == {"dashboard", "email", "sms", "ussd"}

    # Un-acknowledged, the problem must persist: two more ticks, still red.
    sim.step(seeded_db)
    sim.step(seeded_db)
    seeded_db.commit()
    still = [a for a in client.get(f"/api/v1/alerts?site_id={site.id}&active=true",
                                   headers=hdr_op).json() if a["id"] == alert["id"]]
    assert still and still[0]["state"] == "notification_sent"

    # Operator acknowledges from the dashboard...
    res = client.post(f"/api/v1/alerts/{alert['id']}/ack", headers=hdr_op)
    assert res.status_code == 200 and res.json()["state"] == "acknowledged"

    # ...which starts the recovery ramp: within a handful of ticks the pH
    # is back in band and the rule engine marks the alert Resolved. No
    # manual nudge — acknowledgement itself is what fixes the farm.
    alert_now = None
    for _ in range(15):
        sim.step(seeded_db)
        seeded_db.commit()
        alert_now = [a for a in client.get(f"/api/v1/alerts?site_id={site.id}",
                                           headers=hdr_coord).json()
                     if a["id"] == alert["id"]][0]
        if alert_now["state"] == "resolved":
            break
    assert alert_now["state"] == "resolved"
    assert alert_now["resolved_at"] is not None

    # Coordinator closes it; lifecycle complete.
    res = client.post(f"/api/v1/alerts/{alert['id']}/close", headers=hdr_coord)
    assert res.status_code == 200 and res.json()["state"] == "closed"

    # The audit log tells the whole story, in order, with actors.
    audit = client.get("/api/v1/admin/audit?limit=1000", headers=auth(admin_token)).json()
    actions = [e["action"] for e in reversed(audit)]  # oldest first
    for expected in ("watch_started", "alert_raised", "notification_dispatched",
                     "alert_acknowledged", "alert_resolved", "alert_closed"):
        assert expected in actions, f"missing {expected} in audit trail"
    assert actions.index("watch_started") < actions.index("alert_raised") \
        < actions.index("alert_acknowledged") < actions.index("alert_closed")

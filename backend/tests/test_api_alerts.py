"""Black-box tests for the alert endpoints: listing, acknowledgement and
closure, with every RBAC and state-machine refusal the API promises."""

from app.models import AlertState
from tests.conftest import auth, get_site, make_alert


def test_list_alerts_includes_site_name_and_state(client, coordinator_token, seeded_db):
    site = get_site(seeded_db, "GSS Maroua")
    make_alert(seeded_db, site)
    res = client.get("/api/v1/alerts", headers=auth(coordinator_token))
    a = res.json()[0]
    assert a["site_name"] == "GSS Maroua Bottle Farm"
    assert a["state"] == "notification_sent"


def test_active_filter_excludes_closed(client, coordinator_token, seeded_db):
    site = get_site(seeded_db, "GSS Maroua")
    make_alert(seeded_db, site, state=AlertState.closed)
    make_alert(seeded_db, site, state=AlertState.watch)
    res = client.get("/api/v1/alerts?active=true", headers=auth(coordinator_token))
    states = {a["state"] for a in res.json()}
    assert "closed" not in states and "watch" in states


def test_site_filter(client, coordinator_token, seeded_db):
    make_alert(seeded_db, get_site(seeded_db, "GSS Maroua"))
    make_alert(seeded_db, get_site(seeded_db, "Salak"))
    site = get_site(seeded_db, "Salak")
    res = client.get(f"/api/v1/alerts?site_id={site.id}", headers=auth(coordinator_token))
    assert all(a["site_id"] == site.id for a in res.json())
    assert len(res.json()) == 1


# --- acknowledge ---

def test_operator_acks_own_site(client, school_op_token, seeded_db):
    alert = make_alert(seeded_db, get_site(seeded_db, "GSS Maroua"))
    res = client.post(f"/api/v1/alerts/{alert.id}/ack", headers=auth(school_op_token))
    assert res.status_code == 200
    body = res.json()
    assert body["state"] == "acknowledged"
    assert body["acknowledged_at"] is not None
    assert body["acknowledged_by"] is not None


def test_operator_cannot_ack_other_site(client, school_op_token, seeded_db):
    """Business rule: operators only acknowledge on their assigned site."""
    alert = make_alert(seeded_db, get_site(seeded_db, "Makabay"))
    res = client.post(f"/api/v1/alerts/{alert.id}/ack", headers=auth(school_op_token))
    assert res.status_code == 403


def test_coordinator_can_ack_any_site(client, coordinator_token, seeded_db):
    alert = make_alert(seeded_db, get_site(seeded_db, "Makabay"))
    res = client.post(f"/api/v1/alerts/{alert.id}/ack", headers=auth(coordinator_token))
    assert res.status_code == 200


def test_double_ack_is_409(client, coordinator_token, seeded_db):
    alert = make_alert(seeded_db, get_site(seeded_db, "GSS Maroua"))
    client.post(f"/api/v1/alerts/{alert.id}/ack", headers=auth(coordinator_token))
    res = client.post(f"/api/v1/alerts/{alert.id}/ack", headers=auth(coordinator_token))
    assert res.status_code == 409


def test_ack_watch_state_is_409(client, coordinator_token, seeded_db):
    """The state machine has no Watch -> Acknowledged edge; the API must
    refuse rather than corrupt the lifecycle."""
    alert = make_alert(seeded_db, get_site(seeded_db, "GSS Maroua"), state=AlertState.watch)
    res = client.post(f"/api/v1/alerts/{alert.id}/ack", headers=auth(coordinator_token))
    assert res.status_code == 409


def test_ack_unknown_alert_is_404(client, coordinator_token):
    assert client.post("/api/v1/alerts/nope/ack",
                       headers=auth(coordinator_token)).status_code == 404


def test_ack_is_audited(client, school_op_token, admin_token, seeded_db):
    alert = make_alert(seeded_db, get_site(seeded_db, "GSS Maroua"))
    client.post(f"/api/v1/alerts/{alert.id}/ack", headers=auth(school_op_token))
    res = client.get("/api/v1/admin/audit?action=alert_acknowledged", headers=auth(admin_token))
    assert any(e["actor"] == "school_op" for e in res.json())


# --- close ---

def test_coordinator_closes_resolved_alert(client, coordinator_token, seeded_db):
    alert = make_alert(seeded_db, get_site(seeded_db, "GSS Maroua"),
                       state=AlertState.resolved)
    res = client.post(f"/api/v1/alerts/{alert.id}/close", headers=auth(coordinator_token))
    assert res.status_code == 200
    assert res.json()["state"] == "closed"
    assert res.json()["close_reason"] == "closed_by_staff"


def test_operator_cannot_close(client, school_op_token, seeded_db):
    alert = make_alert(seeded_db, get_site(seeded_db, "GSS Maroua"),
                       state=AlertState.resolved)
    res = client.post(f"/api/v1/alerts/{alert.id}/close", headers=auth(school_op_token))
    assert res.status_code == 403


def test_close_unresolved_alert_is_409(client, admin_token, seeded_db):
    alert = make_alert(seeded_db, get_site(seeded_db, "GSS Maroua"),
                       state=AlertState.acknowledged)
    res = client.post(f"/api/v1/alerts/{alert.id}/close", headers=auth(admin_token))
    assert res.status_code == 409

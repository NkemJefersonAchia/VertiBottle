"""Black-box tests for sites, crops, traffic-light status, registration and
threshold management, including the RBAC business rules."""

from app.models import AlertState, SensorNode, utcnow
from app.simulator import Simulator
from tests.conftest import auth, get_site, make_alert


def test_overview_lists_five_seeded_sites(client, coordinator_token):
    res = client.get("/api/v1/sites", headers=auth(coordinator_token))
    assert res.status_code == 200
    sites = res.json()
    assert len(sites) == 5
    assert {s["site_type"] for s in sites} == {"school", "community"}
    assert sum(s["site_type"] == "school" for s in sites) == 3


def test_site_without_readings_shows_offline(client, coordinator_token):
    """Fresh DB, simulator never ran: nodes have no heartbeat, so cards must
    show offline rather than a misleading green (SRS 5.3: operators should
    never be misled by out-of-date data)."""
    res = client.get("/api/v1/sites", headers=auth(coordinator_token))
    assert all(s["status"] == "offline" and not s["node_online"] for s in res.json())


def test_site_goes_green_after_readings(client, coordinator_token, seeded_db):
    Simulator().step(seeded_db)
    seeded_db.commit()
    res = client.get("/api/v1/sites", headers=auth(coordinator_token))
    statuses = {s["name"]: s["status"] for s in res.json()}
    # Drift is random but a single tick can at most create Watches (amber).
    assert all(st in ("green", "amber") for st in statuses.values())


def test_open_watch_shows_amber(client, coordinator_token, seeded_db):
    Simulator().step(seeded_db)
    site = get_site(seeded_db, "Salak")
    make_alert(seeded_db, site, state=AlertState.watch)
    res = client.get(f"/api/v1/sites/{site.id}", headers=auth(coordinator_token))
    assert res.json()["status"] == "amber"


def test_sent_alert_shows_red_and_counts(client, coordinator_token, seeded_db):
    Simulator().step(seeded_db)
    site = get_site(seeded_db, "Salak")
    make_alert(seeded_db, site, state=AlertState.notification_sent)
    res = client.get(f"/api/v1/sites/{site.id}", headers=auth(coordinator_token))
    body = res.json()
    assert body["status"] == "red"
    assert body["active_alerts"] == 1


def test_closed_alerts_do_not_affect_status(client, coordinator_token, seeded_db):
    Simulator().step(seeded_db)
    site = get_site(seeded_db, "Salak")
    make_alert(seeded_db, site, state=AlertState.closed)
    res = client.get(f"/api/v1/sites/{site.id}", headers=auth(coordinator_token))
    assert res.json()["status"] == "green"
    assert res.json()["active_alerts"] == 0


def test_site_detail_includes_profile_and_operators(client, school_op_token, seeded_db):
    site = get_site(seeded_db, "GSS Maroua")
    res = client.get(f"/api/v1/sites/{site.id}", headers=auth(school_op_token))
    body = res.json()
    assert body["crop_profile"]["ph_min"] == 5.5
    assert any(op["username"] == "school_op" for op in body["operators"])


def test_site_detail_unknown_id_is_404(client, admin_token):
    assert client.get("/api/v1/sites/nope", headers=auth(admin_token)).status_code == 404


def test_crops_lists_all_four(client, agronomist_token):
    res = client.get("/api/v1/crops", headers=auth(agronomist_token))
    assert {c["crop_name"] for c in res.json()} == {"lettuce", "spinach", "amaranth", "basil"}


# --- registration (FR 7.1, business rule: admin only) ---

def test_admin_can_register_site(client, admin_token, seeded_db):
    res = client.post("/api/v1/sites", headers=auth(admin_token), json={
        "name": "CES Mora Farm", "site_type": "school",
        "location": "Mora", "crop_name": "basil", "connectivity": "gsm"})
    assert res.status_code == 201
    body = res.json()
    assert body["crop_name"] == "basil"
    # A sensor node is provisioned with the site.
    assert seeded_db.query(SensorNode).filter_by(site_id=body["id"]).count() == 1


def test_non_admin_cannot_register_site(client, coordinator_token, school_op_token):
    for token in (coordinator_token, school_op_token):
        res = client.post("/api/v1/sites", headers=auth(token), json={
            "name": "X", "site_type": "school", "location": "Y", "crop_name": "basil"})
        assert res.status_code == 403


def test_register_with_unknown_crop_is_400(client, admin_token):
    res = client.post("/api/v1/sites", headers=auth(admin_token), json={
        "name": "X", "site_type": "school", "location": "Y", "crop_name": "cassava"})
    assert res.status_code == 400


def test_registration_is_audited(client, admin_token):
    client.post("/api/v1/sites", headers=auth(admin_token), json={
        "name": "Audit Farm", "site_type": "community", "location": "Z", "crop_name": "lettuce"})
    res = client.get("/api/v1/admin/audit?action=site_registered", headers=auth(admin_token))
    assert any("Audit Farm" in e["detail"] for e in res.json())


# --- thresholds (business rule: admin or coordinator; tamper-logged) ---

def test_coordinator_can_update_thresholds(client, coordinator_token, seeded_db):
    site = get_site(seeded_db, "GSS Maroua")
    res = client.patch(f"/api/v1/sites/{site.id}/thresholds",
                       headers=auth(coordinator_token), json={"ph_max": 6.8})
    assert res.status_code == 200
    assert res.json()["ph_max"] == 6.8


def test_operator_cannot_update_thresholds(client, school_op_token, seeded_db):
    site = get_site(seeded_db, "GSS Maroua")
    res = client.patch(f"/api/v1/sites/{site.id}/thresholds",
                       headers=auth(school_op_token), json={"ph_max": 9.9})
    assert res.status_code == 403


def test_threshold_change_tamper_logged_with_old_and_new(client, admin_token, seeded_db):
    """SRS 5.4: threshold changes log operator id, old value, new value."""
    site = get_site(seeded_db, "GSS Maroua")
    client.patch(f"/api/v1/sites/{site.id}/thresholds",
                 headers=auth(admin_token), json={"ph_min": 5.2})
    res = client.get("/api/v1/admin/audit?action=threshold_changed", headers=auth(admin_token))
    entry = res.json()[0]
    assert entry["actor"] == "admin"
    assert "5.5 -> 5.2" in entry["detail"]


def test_threshold_crop_switch(client, admin_token, seeded_db):
    site = get_site(seeded_db, "GSS Maroua")
    res = client.patch(f"/api/v1/sites/{site.id}/thresholds",
                       headers=auth(admin_token), json={"crop_name": "basil"})
    assert res.status_code == 200
    assert res.json()["crop_name"] == "basil"


def test_threshold_unknown_crop_is_400(client, admin_token, seeded_db):
    site = get_site(seeded_db, "GSS Maroua")
    res = client.patch(f"/api/v1/sites/{site.id}/thresholds",
                       headers=auth(admin_token), json={"crop_name": "cassava"})
    assert res.status_code == 400

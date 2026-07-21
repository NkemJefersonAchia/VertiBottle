"""Black-box tests for administration: audit log access and immutability,
node health, and operator management (FR 7.2, FR 8)."""

from datetime import timedelta

from app.models import SensorNode, utcnow
from app.simulator import Simulator
from tests.conftest import auth, get_site, login


# --- audit log (FR 8.1) ---

def test_audit_visible_to_admin_and_coordinator(client, admin_token, coordinator_token):
    for token in (admin_token, coordinator_token):
        assert client.get("/api/v1/admin/audit", headers=auth(token)).status_code == 200


def test_audit_forbidden_for_operators_and_agronomist(client, school_op_token, agronomist_token):
    for token in (school_op_token, agronomist_token):
        assert client.get("/api/v1/admin/audit", headers=auth(token)).status_code == 403


def test_audit_action_filter(client, admin_token):
    res = client.get("/api/v1/admin/audit?action=login", headers=auth(admin_token))
    assert all(e["action"] == "login" for e in res.json())


def test_audit_is_append_only_no_mutation_routes_exist(client, admin_token):
    """Business rule: no audit entry can be edited or deleted, even by
    admins. The API must not even have the routes."""
    # 405 (method not routed; the static-files catch-all only serves GET)
    # or 404 (no such path) both prove the mutation surface doesn't exist.
    assert client.delete("/api/v1/admin/audit", headers=auth(admin_token)).status_code in (404, 405)
    assert client.delete("/api/v1/admin/audit/1", headers=auth(admin_token)).status_code in (404, 405)
    assert client.patch("/api/v1/admin/audit/1", headers=auth(admin_token),
                        json={"detail": "x"}).status_code in (404, 405)
    assert client.post("/api/v1/admin/audit", headers=auth(admin_token),
                       json={"action": "fake"}).status_code in (404, 405)


# --- node health (FR 8.2) ---

def test_health_shows_offline_before_first_reading(client, school_op_token):
    res = client.get("/api/v1/admin/health", headers=auth(school_op_token))
    assert res.status_code == 200  # any role: reliability is everyone's problem
    assert len(res.json()) == 5
    assert all(not n["online"] for n in res.json())


def test_health_online_after_tick_offline_after_silence(client, admin_token, seeded_db):
    Simulator().step(seeded_db)
    seeded_db.commit()
    res = client.get("/api/v1/admin/health", headers=auth(admin_token))
    assert all(n["online"] for n in res.json())

    # Silence one node beyond the freshness window: it must flag offline.
    site = get_site(seeded_db, "GSS Maroua")
    node = seeded_db.query(SensorNode).filter_by(site_id=site.id).one()
    node.last_seen = utcnow() - timedelta(hours=2)
    seeded_db.commit()
    res = client.get("/api/v1/admin/health", headers=auth(admin_token))
    by_site = {n["site_name"]: n["online"] for n in res.json()}
    assert by_site["GSS Maroua Bottle Farm"] is False
    assert by_site["EP Salak School Garden"] is True


# --- user management (FR 7.2) ---

def test_list_users_admin_only(client, admin_token, coordinator_token):
    assert client.get("/api/v1/admin/users", headers=auth(admin_token)).status_code == 200
    assert client.get("/api/v1/admin/users", headers=auth(coordinator_token)).status_code == 403


def test_create_operator_with_full_profile(client, admin_token, seeded_db):
    """FR 7.2: assign role, language, channel, phone, email."""
    site = get_site(seeded_db, "Salak")
    res = client.post("/api/v1/admin/users", headers=auth(admin_token), json={
        "username": "new_op", "password": "pw123456", "name": "New Operator",
        "role": "cb_operator", "site_id": site.id, "phone": "+237699999999",
        "email": None, "language": "fr", "preferred_channel": "ussd"})
    assert res.status_code == 201
    assert res.json()["language"] == "fr"
    # And the new operator can actually log in.
    assert login(client, "new_op", "pw123456")


def test_create_duplicate_username_is_409(client, admin_token):
    payload = {"username": "dup", "password": "x", "name": "D", "role": "agronomist"}
    assert client.post("/api/v1/admin/users", headers=auth(admin_token),
                       json=payload).status_code == 201
    assert client.post("/api/v1/admin/users", headers=auth(admin_token),
                       json=payload).status_code == 409


def test_reassign_operator_site(client, admin_token, seeded_db):
    users = client.get("/api/v1/admin/users", headers=auth(admin_token)).json()
    op = next(u for u in users if u["username"] == "school_op")
    salak = get_site(seeded_db, "Salak")
    res = client.patch(f"/api/v1/admin/users/{op['id']}",
                       headers=auth(admin_token), json={"site_id": salak.id})
    assert res.status_code == 200
    assert res.json()["site_id"] == salak.id


def test_deactivated_user_cannot_log_in_or_use_token(client, admin_token):
    token_before = login(client, "school_op")
    users = client.get("/api/v1/admin/users", headers=auth(admin_token)).json()
    op = next(u for u in users if u["username"] == "school_op")
    client.patch(f"/api/v1/admin/users/{op['id']}",
                 headers=auth(admin_token), json={"active": False})
    # Fresh login refused...
    res = client.post("/api/v1/auth/login",
                      json={"username": "school_op", "password": "demo1234"})
    assert res.status_code == 401
    # ...and the pre-existing token is dead too.
    assert client.get("/api/v1/auth/me", headers=auth(token_before)).status_code == 401


def test_update_unknown_user_is_404(client, admin_token):
    assert client.patch("/api/v1/admin/users/nope", headers=auth(admin_token),
                        json={"active": False}).status_code == 404


def test_user_creation_is_audited(client, admin_token):
    client.post("/api/v1/admin/users", headers=auth(admin_token), json={
        "username": "audited_op", "password": "x", "name": "A", "role": "school_operator"})
    res = client.get("/api/v1/admin/audit?action=operator_created", headers=auth(admin_token))
    assert any("audited_op" in e["detail"] for e in res.json())


# --- meta / static ---

def test_status_endpoint_is_public(client):
    res = client.get("/api/v1/status")
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_frontend_and_vendor_assets_served(client):
    home = client.get("/")
    assert home.status_code == 200
    assert "VertiBottle" in home.text
    assert client.get("/vendor/chart.umd.js").status_code == 200
    assert client.get("/app.js").status_code == 200
    assert client.get("/styles.css").status_code == 200
    # 3D digital-twin assets: the Three.js module and the twin renderer.
    assert client.get("/farm3d.js").status_code == 200
    assert client.get("/vendor/three.module.min.js").status_code == 200

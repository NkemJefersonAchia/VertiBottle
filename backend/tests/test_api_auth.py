"""Black-box tests of the auth contract. Only the HTTP surface is used;
assertions are against documented behaviour (docs/API.md), not internals."""

from tests.conftest import auth, login


def test_login_returns_token_and_user(client):
    res = client.post("/api/v1/auth/login",
                      json={"username": "admin", "password": "demo1234"})
    assert res.status_code == 200
    body = res.json()
    assert body["token"]
    assert body["user"]["username"] == "admin"
    assert body["user"]["role"] == "admin"
    assert "password_hash" not in body["user"]  # never leak hashes


def test_login_wrong_password_is_401(client):
    res = client.post("/api/v1/auth/login",
                      json={"username": "admin", "password": "wrong"})
    assert res.status_code == 401


def test_login_unknown_user_is_401(client):
    res = client.post("/api/v1/auth/login",
                      json={"username": "ghost", "password": "demo1234"})
    assert res.status_code == 401


def test_login_missing_fields_is_422(client):
    assert client.post("/api/v1/auth/login", json={"username": "admin"}).status_code == 422


def test_all_five_roles_can_log_in(client):
    for username in ("school_op", "cb_op", "coordinator", "agronomist", "admin"):
        assert login(client, username)


def test_me_returns_current_user(client, school_op_token):
    res = client.get("/api/v1/auth/me", headers=auth(school_op_token))
    assert res.status_code == 200
    assert res.json()["username"] == "school_op"


def test_protected_endpoint_without_token_is_401(client):
    assert client.get("/api/v1/sites").status_code == 401


def test_protected_endpoint_with_garbage_token_is_401(client):
    assert client.get("/api/v1/sites", headers=auth("not-a-real-token")).status_code == 401


def test_login_is_audited(client, admin_token):
    res = client.get("/api/v1/admin/audit?action=login", headers=auth(admin_token))
    assert res.status_code == 200
    assert any(e["actor"] == "admin" for e in res.json())

"""Black-box tests for the banner feed and the admin outbox."""

from app import notifier
from app.models import AlertState
from tests.conftest import auth, get_site, make_alert


def _dispatch(db, site_fragment="GSS Maroua"):
    site = get_site(db, site_fragment)
    alert = make_alert(db, site, state=AlertState.alert_raised)
    notifier.dispatch(db, alert, site)
    db.commit()
    return alert


def test_operator_sees_own_banner(client, school_op_token, seeded_db):
    _dispatch(seeded_db)
    res = client.get("/api/v1/notifications", headers=auth(school_op_token))
    notes = res.json()
    assert len(notes) == 1
    assert notes[0]["channel"] == "dashboard"
    assert notes[0]["read"] is False


def test_operator_does_not_see_other_sites_banners(client, school_op_token, seeded_db):
    _dispatch(seeded_db, "Makabay")
    res = client.get("/api/v1/notifications", headers=auth(school_op_token))
    assert res.json() == []


def test_coordinator_sees_all_banners(client, coordinator_token, seeded_db):
    _dispatch(seeded_db, "GSS Maroua")
    _dispatch(seeded_db, "Makabay")
    res = client.get("/api/v1/notifications", headers=auth(coordinator_token))
    assert len(res.json()) == 2


def test_mark_read_removes_from_unread_feed(client, school_op_token, seeded_db):
    _dispatch(seeded_db)
    note = client.get("/api/v1/notifications", headers=auth(school_op_token)).json()[0]
    res = client.post(f"/api/v1/notifications/{note['id']}/read",
                      headers=auth(school_op_token))
    assert res.status_code == 204
    assert client.get("/api/v1/notifications", headers=auth(school_op_token)).json() == []
    # Still visible with unread_only=false (history isn't lost).
    all_notes = client.get("/api/v1/notifications?unread_only=false",
                           headers=auth(school_op_token)).json()
    assert len(all_notes) == 1 and all_notes[0]["read"] is True


def test_mark_read_unknown_is_404(client, school_op_token):
    assert client.post("/api/v1/notifications/nope/read",
                       headers=auth(school_op_token)).status_code == 404


def test_outbox_shows_simulated_sends_with_content(client, admin_token, seeded_db):
    """The 'would have sent' log: full message text per channel."""
    _dispatch(seeded_db)
    res = client.get("/api/v1/notifications/outbox", headers=auth(admin_token))
    assert res.status_code == 200
    by_channel = {n["channel"]: n for n in res.json()}
    assert set(by_channel) == {"dashboard", "email", "sms", "ussd"}
    assert by_channel["sms"]["status"] == "simulated"
    assert "VertiBottle ALERT" in by_channel["sms"]["message"]


def test_outbox_channel_filter(client, admin_token, seeded_db):
    _dispatch(seeded_db)
    res = client.get("/api/v1/notifications/outbox?channel=sms", headers=auth(admin_token))
    assert all(n["channel"] == "sms" for n in res.json())
    assert len(res.json()) == 1


def test_outbox_is_admin_only(client, coordinator_token, school_op_token):
    for token in (coordinator_token, school_op_token):
        assert client.get("/api/v1/notifications/outbox",
                          headers=auth(token)).status_code == 403

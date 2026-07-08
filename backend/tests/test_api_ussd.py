"""Black-box tests for the USSD interface (FR 6), asserting the SRS
constraints from the outside: menu tree, 182-char screens, three-press
acknowledgement, language handling, SIM-number binding."""

import pytest

from app.models import AlertState, Parameter
from app.simulator import Simulator
from tests.conftest import get_site, get_user, make_alert

CB_PHONE = "+237650000002"     # cb_op, French, site: Femmes de Makabay
SCHOOL_PHONE = "+237650000001"  # school_op, English, site: GSS Maroua


def dial(client, phone, text=""):
    res = client.post("/api/v1/ussd", json={"phone": phone, "text": text})
    assert res.status_code == 200
    body = res.json()
    # SRS 2.5: every screen must fit the MNO's 182-character limit.
    assert len(body["message"]) <= 182
    return body


def test_unregistered_number_is_refused(client):
    body = dial(client, "+237600000000")
    assert body["end"] is True
    assert "not registered" in body["message"]


def test_menu_matches_srs_tree_in_operator_language(client):
    body = dial(client, CB_PHONE)
    assert body["end"] is False
    for item in ("1.", "2.", "3.", "4.", "0."):
        assert item in body["message"]
    assert "Releve du jour" in body["message"]  # cb_op is French

    body_en = dial(client, SCHOOL_PHONE)
    assert "Today's reading" in body_en["message"]


def test_exit_option(client):
    body = dial(client, CB_PHONE, "0")
    assert body["end"] is True


def test_todays_reading(client, seeded_db):
    Simulator().step(seeded_db)
    seeded_db.commit()
    body = dial(client, SCHOOL_PHONE, "1")
    assert body["end"] is True
    assert "pH" in body["message"]
    assert "GSS Maroua" in body["message"]


def test_current_alerts_when_none(client):
    body = dial(client, CB_PHONE, "2")
    assert body["end"] is True
    assert "Aucune alerte" in body["message"]


def test_current_alerts_lists_active(client, seeded_db):
    site = get_site(seeded_db, "Makabay")
    make_alert(seeded_db, site, parameter=Parameter.ec, trigger_value=2500)
    body = dial(client, CB_PHONE, "2")
    assert "1." in body["message"]
    assert "CE" in body["message"]  # EC in French


def test_acknowledge_in_three_presses(client, seeded_db):
    """NFR 4.2 / FR 6.2: dial, '3', alert number — done."""
    site = get_site(seeded_db, "Makabay")
    alert = make_alert(seeded_db, site)

    step1 = dial(client, CB_PHONE)          # press 0: dial the shortcode
    assert step1["end"] is False
    step2 = dial(client, CB_PHONE, "3")     # press 1: choose "acknowledge"
    assert step2["end"] is False
    assert "1." in step2["message"]
    step3 = dial(client, CB_PHONE, "3*1")   # press 2: pick the alert
    assert step3["end"] is True
    assert "confirmee" in step3["message"]

    seeded_db.expire_all()
    assert seeded_db.get(type(alert), alert.id).state is AlertState.acknowledged


def test_acknowledge_records_operator_in_audit(client, seeded_db):
    from app.models import AuditLog

    make_alert(seeded_db, get_site(seeded_db, "Makabay"))
    dial(client, CB_PHONE, "3*1")
    entry = seeded_db.query(AuditLog).filter_by(action="alert_acknowledged").one()
    assert entry.actor == "cb_op"
    assert "USSD" in entry.detail


def test_acknowledge_only_notification_sent_alerts(client, seeded_db):
    """Watch-state alerts are not yet acknowledgeable; menu must say none."""
    make_alert(seeded_db, get_site(seeded_db, "Makabay"), state=AlertState.watch)
    body = dial(client, CB_PHONE, "3")
    assert body["end"] is True
    assert "Aucune alerte" in body["message"]


def test_acknowledge_bad_index_fails_gracefully(client, seeded_db):
    make_alert(seeded_db, get_site(seeded_db, "Makabay"))
    body = dial(client, CB_PHONE, "3*9")
    assert body["end"] is True
    assert "Impossible" in body["message"]


def test_language_change_persists(client, seeded_db):
    body = dial(client, CB_PHONE, "4")
    assert body["end"] is False
    body = dial(client, CB_PHONE, "4*1")  # switch to English
    assert "English" in body["message"]
    seeded_db.expire_all()
    assert get_user(seeded_db, "cb_op").language == "en"
    # Menus now come up in English.
    assert "Today's reading" in dial(client, CB_PHONE)["message"]


def test_language_invalid_choice(client):
    body = dial(client, CB_PHONE, "4*7")
    assert body["end"] is True


def test_invalid_menu_choice(client):
    body = dial(client, CB_PHONE, "8")
    assert body["end"] is True


def test_operator_without_site_gets_no_site_message(client, seeded_db):
    op = get_user(seeded_db, "cb_op")
    op.site_id = None
    seeded_db.commit()
    for choice in ("1", "2", "3"):
        body = dial(client, CB_PHONE, choice)
        assert body["end"] is True


@pytest.mark.parametrize("choice", ["", "1", "2", "3", "4", "0"])
def test_every_screen_fits_182_chars_with_data(client, seeded_db, choice):
    """Run the whole tree with live readings and several alerts stacked up —
    the length cap must hold on the busiest screens, not just the menu."""
    sim = Simulator()
    for _ in range(2):
        sim.step(seeded_db)
    site = get_site(seeded_db, "Makabay")
    for i, param in enumerate([Parameter.ph, Parameter.ec, Parameter.humidity,
                               Parameter.light, Parameter.water_level]):
        make_alert(seeded_db, site, parameter=param, trigger_value=1 + i)
    seeded_db.commit()
    dial(client, CB_PHONE, choice)  # dial() asserts the 182-char cap

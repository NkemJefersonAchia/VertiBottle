"""Black-box tests for the readings series (dashboard poll) and CSV export."""

from app.simulator import Simulator
from tests.conftest import auth, get_site


def test_series_shape_before_any_readings(client, school_op_token, seeded_db):
    site = get_site(seeded_db, "GSS Maroua")
    res = client.get(f"/api/v1/readings?site_id={site.id}", headers=auth(school_op_token))
    assert res.status_code == 200
    series = res.json()
    assert len(series) == 7  # always all parameters, even when empty
    for s in series:
        assert s["points"] == []
        assert s["latest"] is None and s["in_band"] is None
        assert s["band_min"] < s["band_max"]


def test_series_after_ticks(client, school_op_token, seeded_db):
    sim = Simulator()
    for _ in range(3):
        sim.step(seeded_db)
    seeded_db.commit()
    site = get_site(seeded_db, "GSS Maroua")
    res = client.get(f"/api/v1/readings?site_id={site.id}&hours=24",
                     headers=auth(school_op_token))
    for s in res.json():
        assert len(s["points"]) == 3
        assert s["latest"] == s["points"][-1]["value"]
        assert isinstance(s["in_band"], bool)


def test_series_unknown_site_is_404(client, school_op_token):
    assert client.get("/api/v1/readings?site_id=nope",
                      headers=auth(school_op_token)).status_code == 404


def test_series_requires_site_id(client, school_op_token):
    assert client.get("/api/v1/readings", headers=auth(school_op_token)).status_code == 422


def test_export_csv_for_agronomist(client, agronomist_token, seeded_db):
    Simulator().step(seeded_db)
    seeded_db.commit()
    site = get_site(seeded_db, "GSS Maroua")
    res = client.get(f"/api/v1/readings/export.csv?site_id={site.id}",
                     headers=auth(agronomist_token))
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    lines = res.text.strip().splitlines()
    assert lines[0] == "timestamp_utc,site,parameter,value"
    assert len(lines) == 1 + 7  # one tick -> 7 readings


def test_export_csv_forbidden_for_operators(client, school_op_token, seeded_db):
    site = get_site(seeded_db, "GSS Maroua")
    res = client.get(f"/api/v1/readings/export.csv?site_id={site.id}",
                     headers=auth(school_op_token))
    assert res.status_code == 403

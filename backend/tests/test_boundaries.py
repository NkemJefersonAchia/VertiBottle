"""Boundary-value analysis on the band check (testing principle 2:
exhaustive testing is impossible, so test the equivalence-class edges where
off-by-one defects live).

The contract: a reading is in-band iff band_min <= value <= band_max —
edges inclusive. Lettuce pH band is 5.5–6.5.
"""

import pytest

from app import rule_engine
from app.models import AlertState, Parameter, Reading
from tests.conftest import get_site

EPS = 1e-9


def _evaluate(db, site, value):
    r = Reading(site_id=site.id, node_id=site.sensor_node.id,
                parameter=Parameter.ph, value=value)
    db.add(r)
    db.flush()
    return rule_engine.evaluate(db, r, site)


@pytest.mark.parametrize("value", [5.5, 6.5, 6.0])          # on-edge and middle
def test_values_on_band_edges_are_in_band(seeded_db, value):
    site = get_site(seeded_db, "GSS Maroua")
    assert _evaluate(seeded_db, site, value) is None


@pytest.mark.parametrize("value", [5.5 - EPS, 6.5 + EPS, 0.0, 14.0])
def test_values_just_outside_band_start_watch(seeded_db, value):
    site = get_site(seeded_db, "GSS Maroua")
    alert = _evaluate(seeded_db, site, value)
    assert alert is not None
    assert alert.state is AlertState.watch

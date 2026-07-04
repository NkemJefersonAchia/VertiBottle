"""Unit tests for the alert lifecycle — the one piece of logic where a bug
silently breaks the whole product promise (SRS 5.5: maximum reliability)."""

import pytest

from app.models import Alert, AlertState, Parameter
from app.state_machine import IllegalTransition, transition


def make_alert(state=AlertState.watch):
    return Alert(
        site_id="s", parameter=Parameter.ph, state=state,
        trigger_value=4.8, band_min=5.5, band_max=6.5,
    )


def test_happy_path_full_lifecycle():
    a = make_alert()
    for target in (AlertState.alert_raised, AlertState.notification_sent,
                   AlertState.acknowledged, AlertState.resolved, AlertState.closed):
        transition(a, target)
    assert a.state is AlertState.closed
    assert a.raised_at and a.notified_at and a.acknowledged_at
    assert a.resolved_at and a.closed_at


def test_timeout_shortcut_from_notification_sent():
    a = make_alert(AlertState.notification_sent)
    transition(a, AlertState.closed)
    assert a.state is AlertState.closed


def test_watch_can_close_as_false_alarm():
    a = make_alert(AlertState.watch)
    transition(a, AlertState.closed)
    assert a.state is AlertState.closed


def test_cannot_skip_notification_to_acknowledge():
    a = make_alert(AlertState.alert_raised)
    with pytest.raises(IllegalTransition):
        transition(a, AlertState.acknowledged)


def test_cannot_resolve_without_acknowledgement():
    a = make_alert(AlertState.notification_sent)
    with pytest.raises(IllegalTransition):
        transition(a, AlertState.resolved)


def test_closed_is_terminal():
    a = make_alert(AlertState.notification_sent)
    transition(a, AlertState.closed)
    for target in AlertState:
        if target is AlertState.closed:
            continue
        with pytest.raises(IllegalTransition):
            transition(a, target)


def test_timestamps_stamped_per_state():
    a = make_alert()
    assert a.raised_at is None
    transition(a, AlertState.alert_raised)
    assert a.raised_at is not None
    assert a.notified_at is None

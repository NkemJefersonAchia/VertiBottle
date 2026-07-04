"""Alert lifecycle state machine (SRS Appendix B, Diagram 4).

    Normal -> Watch -> Alert Raised -> Notification Sent -> Acknowledged
           -> Resolved -> Closed

plus the shortcut  Notification Sent -> Closed  on timeoutExpired.

This module owns the *legality* of transitions; rule_engine.py decides
*when* to fire them based on incoming readings, and the API fires the
operator-driven ones (acknowledge, close). Keeping legality in one place
means an illegal jump (e.g. Watch -> Acknowledged) can never be introduced
by a new endpoint without failing loudly here.
"""

from datetime import datetime

from .models import Alert, AlertState, utcnow

# state -> set of states it may move to
TRANSITIONS: dict[AlertState, set[AlertState]] = {
    AlertState.normal: {AlertState.watch},
    AlertState.watch: {AlertState.alert_raised, AlertState.closed},
    AlertState.alert_raised: {AlertState.notification_sent},
    AlertState.notification_sent: {AlertState.acknowledged, AlertState.closed},
    AlertState.acknowledged: {AlertState.resolved},
    AlertState.resolved: {AlertState.closed},
    AlertState.closed: set(),
}

# Note: Watch -> Closed is not in the SRS diagram (which only tracks alerts
# from Alert Raised onward). We persist the Watch stage as an Alert row so
# the dashboard can show amber early, so we need a way to retire a Watch
# whose next reading came back in band — that is a false-alarm dismissal,
# recorded with close_reason="recovered_in_watch".


class IllegalTransition(Exception):
    pass


def transition(alert: Alert, to_state: AlertState, *, when: datetime | None = None) -> Alert:
    """Move an alert to a new state, stamping the matching timestamp column."""
    if to_state not in TRANSITIONS[alert.state]:
        raise IllegalTransition(f"{alert.state.value} -> {to_state.value} is not allowed")

    now = when or utcnow()
    alert.state = to_state
    if to_state is AlertState.alert_raised:
        alert.raised_at = now
    elif to_state is AlertState.notification_sent:
        alert.notified_at = now
    elif to_state is AlertState.acknowledged:
        alert.acknowledged_at = now
    elif to_state is AlertState.resolved:
        alert.resolved_at = now
    elif to_state is AlertState.closed:
        alert.closed_at = now
    return alert

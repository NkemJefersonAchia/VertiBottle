"""Alert list, acknowledgement and closure (FR 4/FR 5 operator side)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import audit
from ..database import get_db
from ..models import Alert, AlertState, Role, Site, User
from ..rule_engine import OPEN_STATES
from ..schemas import AlertOut
from ..security import current_user, require_roles
from ..state_machine import IllegalTransition, transition

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


def _with_site_name(alert: Alert, site_names: dict[str, str]) -> AlertOut:
    out = AlertOut.model_validate(alert)
    out.site_name = site_names.get(alert.site_id)
    return out


@router.get("", response_model=list[AlertOut])
def list_alerts(site_id: str | None = None, active: bool = False, limit: int = 100,
                db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = select(Alert).order_by(Alert.created_at.desc()).limit(limit)
    if site_id:
        q = q.where(Alert.site_id == site_id)
    if active:
        q = q.where(Alert.state.in_(OPEN_STATES))
    alerts = db.scalars(q).all()
    site_names = {s.id: s.name for s in db.scalars(select(Site)).all()}
    return [_with_site_name(a, site_names) for a in alerts]


@router.post("/{alert_id}/ack", response_model=AlertOut)
def acknowledge(alert_id: str, db: Session = Depends(get_db),
                user: User = Depends(current_user)):
    """operatorAcknowledgement: Notification Sent -> Acknowledged.

    Business rule: an operator may only acknowledge alerts on the site they
    are assigned to. Coordinators and admins may acknowledge anywhere (they
    manage multiple sites)."""
    alert = db.scalar(
        select(Alert).where(Alert.id == alert_id).options(selectinload(Alert.site))
    )
    if alert is None:
        raise HTTPException(404, "Alert not found")

    is_staff = user.role in (Role.admin, Role.coordinator)
    if not is_staff and user.site_id != alert.site_id:
        raise HTTPException(403, "You can only acknowledge alerts for your own site")

    try:
        transition(alert, AlertState.acknowledged)
    except IllegalTransition as e:
        raise HTTPException(409, str(e))
    alert.acknowledged_by = user.id
    audit.log(db, user.username, "alert_acknowledged",
              f"{alert.parameter.value} alert on {alert.site.name}", alert.site_id)
    db.commit()
    out = AlertOut.model_validate(alert)
    out.site_name = alert.site.name
    return out


@router.post("/{alert_id}/close", response_model=AlertOut)
def close(alert_id: str, db: Session = Depends(get_db),
          user: User = Depends(require_roles(Role.coordinator, Role.admin))):
    """closeAlert: Resolved -> Closed. Restricted to coordinator/admin per
    the state machine ('coordinator or admin closes the alert')."""
    alert = db.scalar(
        select(Alert).where(Alert.id == alert_id).options(selectinload(Alert.site))
    )
    if alert is None:
        raise HTTPException(404, "Alert not found")
    try:
        transition(alert, AlertState.closed)
    except IllegalTransition as e:
        raise HTTPException(409, str(e))
    alert.close_reason = "closed_by_staff"
    audit.log(db, user.username, "alert_closed",
              f"{alert.parameter.value} alert on {alert.site.name}", alert.site_id)
    db.commit()
    out = AlertOut.model_validate(alert)
    out.site_name = alert.site.name
    return out

"""Notification feed. The dashboard banner polls the unread dashboard-channel
rows for the logged-in user; the admin dev panel reads everything, including
the simulated email/SMS/USSD payloads (see notifier.py for why they are
simulated)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Channel, Notification, Role, Site, User
from ..schemas import NotificationOut
from ..security import ADMIN_ONLY, current_user

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


def _enrich(db: Session, notes: list[Notification]) -> list[NotificationOut]:
    """Attach the alert's structured facts and the site name so clients can
    localise the text themselves (see NotificationOut)."""
    site_names = {s.id: s.name for s in db.scalars(select(Site)).all()}
    out = []
    for n in notes:
        item = NotificationOut.model_validate(n)
        item.site_name = site_names.get(n.site_id)
        if n.alert is not None:
            item.parameter = n.alert.parameter
            item.trigger_value = n.alert.trigger_value
            item.band_min = n.alert.band_min
            item.band_max = n.alert.band_max
        out.append(item)
    return out


@router.get("", response_model=list[NotificationOut])
def my_banner_feed(unread_only: bool = True, limit: int = 20,
                   db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Dashboard-channel notifications addressed to the current user.
    Coordinators and admins see banners for all sites (recipient match is
    skipped for them since they oversee the whole programme)."""
    q = (select(Notification)
         .options(selectinload(Notification.alert))
         .where(Notification.channel == Channel.dashboard)
         .order_by(Notification.sent_at.desc())
         .limit(limit))
    if user.role not in (Role.admin, Role.coordinator):
        q = q.where(Notification.recipient == user.username)
    if unread_only:
        q = q.where(Notification.read.is_(False))
    return _enrich(db, db.scalars(q).all())


@router.post("/{notification_id}/read", status_code=204)
def mark_read(notification_id: str, db: Session = Depends(get_db),
              user: User = Depends(current_user)):
    note = db.get(Notification, notification_id)
    if note is None:
        raise HTTPException(404, "Notification not found")
    note.read = True
    db.commit()


@router.get("/outbox", response_model=list[NotificationOut])
def outbox(channel: Channel | None = None, limit: int = 100,
           db: Session = Depends(get_db), user: User = ADMIN_ONLY):
    """Admin dev panel: every dispatched notification on every channel,
    including the full message content of the simulated email/SMS/USSD
    sends ('would have sent' log)."""
    q = (select(Notification)
         .options(selectinload(Notification.alert))
         .order_by(Notification.sent_at.desc())
         .limit(limit))
    if channel:
        q = q.where(Notification.channel == channel)
    return _enrich(db, db.scalars(q).all())

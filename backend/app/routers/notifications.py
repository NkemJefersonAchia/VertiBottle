"""Notification feed. The dashboard banner polls the unread dashboard-channel
rows for the logged-in user; the admin dev panel reads everything, including
the simulated email/SMS/USSD payloads (see notifier.py for why they are
simulated)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Channel, Notification, Role, User
from ..schemas import NotificationOut
from ..security import ADMIN_ONLY, current_user

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def my_banner_feed(unread_only: bool = True, limit: int = 20,
                   db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Dashboard-channel notifications addressed to the current user.
    Coordinators and admins see banners for all sites (recipient match is
    skipped for them since they oversee the whole programme)."""
    q = (select(Notification)
         .where(Notification.channel == Channel.dashboard)
         .order_by(Notification.sent_at.desc())
         .limit(limit))
    if user.role not in (Role.admin, Role.coordinator):
        q = q.where(Notification.recipient == user.username)
    if unread_only:
        q = q.where(Notification.read.is_(False))
    return db.scalars(q).all()


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
    q = select(Notification).order_by(Notification.sent_at.desc()).limit(limit)
    if channel:
        q = q.where(Notification.channel == channel)
    return db.scalars(q).all()

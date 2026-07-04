"""Administration endpoints (FR 7.2, FR 8): operator management, audit log
viewing, node health. Audit log is read-only by design — there is no write
endpoint (the backend appends internally) and no update/delete anywhere."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import audit
from ..config import settings
from ..database import get_db
from ..models import AuditLog, Role, SensorNode, Site, User, utcnow
from ..schemas import AuditEntry, NodeHealth, OperatorCreate, OperatorUpdate, UserOut
from ..security import ADMIN_ONLY, current_user, hash_password, require_roles

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/audit", response_model=list[AuditEntry])
def audit_log(action: str | None = None, site_id: str | None = None, limit: int = 200,
              db: Session = Depends(get_db),
              user: User = Depends(require_roles(Role.admin, Role.coordinator))):
    """Append-only audit trail (FR 8.1). Filterable by action type so the
    demo can show e.g. only threshold changes or only acknowledgements."""
    q = select(AuditLog).order_by(AuditLog.ts.desc()).limit(min(limit, 1000))
    if action:
        q = q.where(AuditLog.action == action)
    if site_id:
        q = q.where(AuditLog.site_id == site_id)
    return db.scalars(q).all()


@router.get("/health", response_model=list[NodeHealth])
def node_health(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """FR 8.2: which nodes are up and when they last reported. Any logged-in
    role may check this — reliability is everyone's problem (SRS 5.5)."""
    nodes = db.scalars(select(SensorNode).options(selectinload(SensorNode.site))).all()
    out = []
    for n in nodes:
        online = bool(
            n.last_seen
            and (utcnow() - n.last_seen) < timedelta(seconds=settings.NODE_OFFLINE_AFTER_SECONDS)
        )
        out.append(NodeHealth(
            site_id=n.site_id, site_name=n.site.name, node_id=n.id,
            connectivity=n.connectivity, last_seen=n.last_seen, online=online,
        ))
    return out


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), user: User = ADMIN_ONLY):
    return db.scalars(select(User)).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: OperatorCreate, db: Session = Depends(get_db), user: User = ADMIN_ONLY):
    if db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(409, "Username already exists")
    new = User(
        username=body.username,
        password_hash=hash_password(body.password),
        name=body.name,
        role=body.role,
        site_id=body.site_id,
        phone=body.phone,
        email=body.email,
        language=body.language,
        preferred_channel=body.preferred_channel,
    )
    db.add(new)
    audit.log(db, user.username, "operator_created",
              f"{body.username} ({body.role.value}) site={body.site_id}", body.site_id)
    db.commit()
    return new


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: str, body: OperatorUpdate,
                db: Session = Depends(get_db), user: User = ADMIN_ONLY):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(404, "User not found")
    changes = body.model_dump(exclude_none=True)
    for field, value in changes.items():
        setattr(target, field, value)
    audit.log(db, user.username, "operator_updated",
              f"{target.username}: {changes}", target.site_id)
    db.commit()
    return target

"""Site endpoints: overview cards, per-site detail, registration and
threshold management (FR 3, FR 7)."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import audit
from ..config import settings
from ..database import get_db
from ..models import (
    Alert,
    AlertState,
    CropProfile,
    SensorNode,
    Site,
    User,
    utcnow,
)
from ..rule_engine import OPEN_STATES
from ..schemas import (
    CropProfileOut,
    SiteCard,
    SiteCreate,
    SiteDetail,
    ThresholdUpdate,
    UserOut,
)
from ..security import ADMIN_ONLY, THRESHOLD_MANAGERS, current_user

router = APIRouter(prefix="/api/v1", tags=["sites"])

# Dashboard traffic light: red = a confirmed alert needs attention,
# amber = something is being watched or was acknowledged but not yet
# resolved, green = all channels in band, offline = node gone quiet.
RED_STATES = {AlertState.alert_raised, AlertState.notification_sent}
AMBER_STATES = {AlertState.watch, AlertState.acknowledged}


def _site_status(site: Site, open_alerts: list[Alert]) -> tuple[str, bool]:
    node = site.sensor_node
    online = bool(
        node and node.last_seen
        and (utcnow() - node.last_seen) < timedelta(seconds=settings.NODE_OFFLINE_AFTER_SECONDS)
    )
    if not online:
        return "offline", False
    states = {a.state for a in open_alerts}
    if states & RED_STATES:
        return "red", True
    if states & AMBER_STATES:
        return "amber", True
    return "green", True


def _card(site: Site, open_alerts: list[Alert]) -> SiteCard:
    status, online = _site_status(site, open_alerts)
    node = site.sensor_node
    return SiteCard(
        id=site.id,
        name=site.name,
        site_type=site.site_type,
        location=site.location,
        crop_name=site.crop_profile.crop_name,
        status=status,
        active_alerts=len(open_alerts),
        last_updated=node.last_seen if node else None,
        node_online=online,
    )


def _open_alerts_by_site(db: Session) -> dict[str, list[Alert]]:
    rows = db.scalars(select(Alert).where(Alert.state.in_(OPEN_STATES))).all()
    grouped: dict[str, list[Alert]] = {}
    for a in rows:
        grouped.setdefault(a.site_id, []).append(a)
    return grouped


@router.get("/sites", response_model=list[SiteCard])
def list_sites(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Multi-site overview (Programme Coordinator landing screen). All roles
    may read it; operators just see their own site highlighted client-side."""
    sites = db.scalars(
        select(Site).options(selectinload(Site.crop_profile), selectinload(Site.sensor_node))
    ).all()
    grouped = _open_alerts_by_site(db)
    return [_card(s, grouped.get(s.id, [])) for s in sites]


@router.get("/sites/{site_id}", response_model=SiteDetail)
def site_detail(site_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    site = db.get(Site, site_id)
    if site is None:
        raise HTTPException(404, "Site not found")
    grouped = _open_alerts_by_site(db)
    card = _card(site, grouped.get(site.id, []))
    return SiteDetail(
        **card.model_dump(),
        crop_profile=CropProfileOut.model_validate(site.crop_profile),
        operators=[UserOut.model_validate(u) for u in site.operators],
    )


@router.get("/crops", response_model=list[CropProfileOut])
def list_crops(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return db.scalars(select(CropProfile)).all()


@router.post("/sites", response_model=SiteDetail, status_code=201)
def register_site(body: SiteCreate, db: Session = Depends(get_db), user: User = ADMIN_ONLY):
    """Business rule: only an administrator may register a site. Registering
    always configures crop thresholds (use-case «include» relationship) —
    here by attaching the chosen crop profile."""
    crop = db.scalar(select(CropProfile).where(CropProfile.crop_name == body.crop_name))
    if crop is None:
        raise HTTPException(400, f"Unknown crop: {body.crop_name}")
    site = Site(name=body.name, site_type=body.site_type, location=body.location,
                crop_profile=crop, verified=True)
    db.add(site)
    db.add(SensorNode(site=site, connectivity=body.connectivity))
    audit.log(db, user.username, "site_registered",
              f"{body.name} ({body.site_type.value}) in {body.location}, crop={body.crop_name}")
    db.commit()
    return site_detail(site.id, db, user)


@router.patch("/sites/{site_id}/thresholds", response_model=CropProfileOut)
def update_thresholds(site_id: str, body: ThresholdUpdate,
                      db: Session = Depends(get_db), user: User = THRESHOLD_MANAGERS):
    """Business rule: crop/threshold changes are admin or coordinator only.
    Every field change is tamper-logged with operator id, old and new value
    (SRS 5.4). Note this edits the site's crop profile in place — profiles
    are shared across sites with the same crop, so in this pilot a change
    applies to all sites growing that crop; per-site overrides are a v1.1
    item recorded in ARCHITECTURE.md."""
    site = db.get(Site, site_id)
    if site is None:
        raise HTTPException(404, "Site not found")

    if body.crop_name:
        crop = db.scalar(select(CropProfile).where(CropProfile.crop_name == body.crop_name))
        if crop is None:
            raise HTTPException(400, f"Unknown crop: {body.crop_name}")
        audit.log(db, user.username, "threshold_changed",
                  f"crop switched {site.crop_profile.crop_name} -> {crop.crop_name}", site.id)
        site.crop_profile = crop

    profile = site.crop_profile
    for field, new_value in body.model_dump(exclude_none=True, exclude={"crop_name"}).items():
        old_value = getattr(profile, field)
        if old_value != new_value:
            setattr(profile, field, new_value)
            audit.log(db, user.username, "threshold_changed",
                      f"{profile.crop_name}.{field}: {old_value:g} -> {new_value:g}", site.id)
    db.commit()
    db.refresh(profile)
    return profile

"""Reading queries for the dashboard charts (FR 3.1) and CSV export for
agronomists (use case: Export Data)."""

import csv
import io
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Parameter, Reading, Role, Site, User, utcnow
from ..schemas import ParameterSeries, ReadingPoint
from ..security import current_user, require_roles

router = APIRouter(prefix="/api/v1/readings", tags=["readings"])


@router.get("", response_model=list[ParameterSeries])
def series(site_id: str, hours: int = 24,
           db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Time series per parameter for one site — the endpoint the dashboard
    polls every ~30 s (SRS 2.1 step 10). Returns every parameter with its
    target band so the frontend can shade the healthy zone."""
    site = db.get(Site, site_id)
    if site is None:
        raise HTTPException(404, "Site not found")
    since = utcnow() - timedelta(hours=hours)

    rows = db.scalars(
        select(Reading)
        .where(Reading.site_id == site_id, Reading.ts >= since)
        .order_by(Reading.ts)
    ).all()

    by_param: dict[Parameter, list[Reading]] = {p: [] for p in Parameter}
    for r in rows:
        by_param[r.parameter].append(r)

    out: list[ParameterSeries] = []
    for param in Parameter:
        band_min, band_max = site.crop_profile.band(param)
        points = by_param[param]
        latest = points[-1] if points else None
        out.append(ParameterSeries(
            parameter=param,
            band_min=band_min,
            band_max=band_max,
            latest=latest.value if latest else None,
            latest_ts=latest.ts if latest else None,
            in_band=(band_min <= latest.value <= band_max) if latest else None,
            points=[ReadingPoint(ts=r.ts, value=r.value) for r in points],
        ))
    return out


@router.get("/export.csv")
def export_csv(site_id: str, days: int = 30,
               db: Session = Depends(get_db),
               user: User = Depends(require_roles(
                   Role.agronomist, Role.coordinator, Role.admin))):
    """CSV export of raw readings (agronomist/researcher use case). Limited
    to the staff roles; operators work from the charts."""
    site = db.get(Site, site_id)
    if site is None:
        raise HTTPException(404, "Site not found")
    since = utcnow() - timedelta(days=days)
    rows = db.scalars(
        select(Reading)
        .where(Reading.site_id == site_id, Reading.ts >= since)
        .order_by(Reading.ts)
    ).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["timestamp_utc", "site", "parameter", "value"])
    for r in rows:
        writer.writerow([r.ts.isoformat(), site.name, r.parameter.value, r.value])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition":
                 f'attachment; filename="{site.name.replace(" ", "_")}_readings.csv"'},
    )

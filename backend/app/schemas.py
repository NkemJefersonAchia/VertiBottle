"""Pydantic request/response shapes for the REST API (/api/v1)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from .models import AlertState, Channel, Parameter, Role, SiteType


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    username: str
    name: str
    role: Role
    language: str
    preferred_channel: Channel
    site_id: str | None
    phone: str | None
    email: str | None
    active: bool


class LoginResponse(BaseModel):
    token: str
    user: UserOut


class CropProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    crop_name: str
    ph_min: float
    ph_max: float
    ec_min: float
    ec_max: float
    water_temp_min: float
    water_temp_max: float
    air_temp_min: float
    air_temp_max: float
    humidity_min: float
    humidity_max: float
    water_level_min: float
    water_level_max: float
    light_min: float
    light_max: float


class SiteCard(BaseModel):
    """One card on the multi-site overview."""
    id: str
    name: str
    site_type: SiteType
    location: str
    crop_name: str
    status: str  # green | amber | red | offline
    active_alerts: int
    last_updated: datetime | None
    node_online: bool


class SiteDetail(SiteCard):
    crop_profile: CropProfileOut
    operators: list[UserOut]


class SiteCreate(BaseModel):
    name: str
    site_type: SiteType
    location: str
    crop_name: str
    connectivity: str = "wifi"


class ThresholdUpdate(BaseModel):
    """Partial update of the site's crop band. Only provided fields change;
    every change is tamper-logged with old and new values (SRS 5.4)."""
    ph_min: float | None = None
    ph_max: float | None = None
    ec_min: float | None = None
    ec_max: float | None = None
    water_temp_min: float | None = None
    water_temp_max: float | None = None
    air_temp_min: float | None = None
    air_temp_max: float | None = None
    humidity_min: float | None = None
    humidity_max: float | None = None
    water_level_min: float | None = None
    water_level_max: float | None = None
    light_min: float | None = None
    light_max: float | None = None
    crop_name: str | None = None  # switch the site to a different crop entirely


class ReadingPoint(BaseModel):
    ts: datetime
    value: float


class ParameterSeries(BaseModel):
    parameter: Parameter
    band_min: float
    band_max: float
    latest: float | None
    latest_ts: datetime | None
    in_band: bool | None
    points: list[ReadingPoint]


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    site_id: str
    parameter: Parameter
    state: AlertState
    severity: str
    trigger_value: float
    band_min: float
    band_max: float
    created_at: datetime
    raised_at: datetime | None
    notified_at: datetime | None
    acknowledged_at: datetime | None
    acknowledged_by: str | None
    resolved_at: datetime | None
    closed_at: datetime | None
    close_reason: str | None
    site_name: str | None = None


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    alert_id: str
    site_id: str
    channel: Channel
    recipient: str
    message: str
    status: str
    sent_at: datetime
    read: bool
    # Structured alert facts, so the dashboard can compose the banner text
    # in the viewer's current UI language instead of showing the stored
    # `message` (which is fixed in the recipient's language at send time —
    # the right record for the outbox, the wrong thing for a banner).
    site_name: str | None = None
    parameter: Parameter | None = None
    trigger_value: float | None = None
    band_min: float | None = None
    band_max: float | None = None


class AuditEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ts: datetime
    actor: str
    action: str
    detail: str
    site_id: str | None


class NodeHealth(BaseModel):
    site_id: str
    site_name: str
    node_id: str
    connectivity: str
    last_seen: datetime | None
    online: bool


class UssdRequest(BaseModel):
    """Mimics an Africa's Talking-style USSD webhook: `text` accumulates the
    user's keypresses joined by '*' over one session."""
    phone: str
    text: str = ""


class UssdResponse(BaseModel):
    message: str  # what the phone screen shows (<= 182 chars, SRS 2.5)
    end: bool     # True = session terminated (CON/END in aggregator terms)


class OperatorCreate(BaseModel):
    username: str
    password: str
    name: str
    role: Role
    site_id: str | None = None
    phone: str | None = None
    email: str | None = None
    language: str = "en"
    preferred_channel: Channel = Channel.dashboard


class OperatorUpdate(BaseModel):
    site_id: str | None = None
    phone: str | None = None
    email: str | None = None
    language: str | None = None
    preferred_channel: Channel | None = None
    active: bool | None = None

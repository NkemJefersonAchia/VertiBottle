"""SQLAlchemy models.

These mirror the SRS Appendix B class diagram. One deliberate divergence:
the diagram models Operator/Administrator/ProgrammeCoordinator/Agronomist
as subclasses of User. In the database we use a single `users` table with a
`role` column instead of joined-table inheritance — the subclasses carry no
extra persistent state, only behaviour, so separate tables would add joins
for nothing. docs/ARCHITECTURE.md records this and the other divergences.
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Role(str, enum.Enum):
    school_operator = "school_operator"
    cb_operator = "cb_operator"
    coordinator = "coordinator"
    agronomist = "agronomist"
    admin = "admin"


class SiteType(str, enum.Enum):
    school = "school"
    community = "community"


class Parameter(str, enum.Enum):
    ph = "ph"
    ec = "ec"
    water_temp = "water_temp"
    air_temp = "air_temp"
    humidity = "humidity"
    water_level = "water_level"
    light = "light"


class AlertState(str, enum.Enum):
    # Full lifecycle from the SRS state machine diagram. `normal` never
    # appears on a persisted Alert row (no alert exists while readings are
    # in band); it exists here so the state machine module can name it.
    normal = "normal"
    watch = "watch"
    alert_raised = "alert_raised"
    notification_sent = "notification_sent"
    acknowledged = "acknowledged"
    resolved = "resolved"
    closed = "closed"


class Channel(str, enum.Enum):
    dashboard = "dashboard"
    email = "email"
    sms = "sms"
    ussd = "ussd"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    name: Mapped[str] = mapped_column(String(128))
    role: Mapped[Role] = mapped_column(Enum(Role))
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(128), nullable=True)
    language: Mapped[str] = mapped_column(String(2), default="en")  # en | fr
    preferred_channel: Mapped[Channel] = mapped_column(Enum(Channel), default=Channel.dashboard)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    site_id: Mapped[str | None] = mapped_column(
        ForeignKey("sites.id"), nullable=True
    )  # operators are assigned to one site; staff roles have none
    site: Mapped["Site | None"] = relationship(back_populates="operators")


class AuthToken(Base):
    """Opaque bearer tokens. Deliberately simple — the SRS-level auth
    (bcrypt cost 12, 2FA for admins) is out of scope for the demo, but the
    role checks behind these tokens are enforced at the API layer for real."""

    __tablename__ = "auth_tokens"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship()


class CropProfile(Base):
    __tablename__ = "crop_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    crop_name: Mapped[str] = mapped_column(String(64), unique=True)
    # Target bands per parameter. Readings outside [min, max] are out-of-band.
    ph_min: Mapped[float] = mapped_column(Float)
    ph_max: Mapped[float] = mapped_column(Float)
    ec_min: Mapped[float] = mapped_column(Float)      # µS/cm
    ec_max: Mapped[float] = mapped_column(Float)
    water_temp_min: Mapped[float] = mapped_column(Float)  # °C
    water_temp_max: Mapped[float] = mapped_column(Float)
    air_temp_min: Mapped[float] = mapped_column(Float)    # °C
    air_temp_max: Mapped[float] = mapped_column(Float)
    humidity_min: Mapped[float] = mapped_column(Float)    # %RH
    humidity_max: Mapped[float] = mapped_column(Float)
    water_level_min: Mapped[float] = mapped_column(Float)  # cm from sensor: lower = fuller
    water_level_max: Mapped[float] = mapped_column(Float)
    light_min: Mapped[float] = mapped_column(Float)        # lux
    light_max: Mapped[float] = mapped_column(Float)

    def band(self, parameter: "Parameter") -> tuple[float, float]:
        p = parameter.value
        return getattr(self, f"{p}_min"), getattr(self, f"{p}_max")


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(128))
    site_type: Mapped[SiteType] = mapped_column(Enum(SiteType))
    location: Mapped[str] = mapped_column(String(128))
    verified: Mapped[bool] = mapped_column(Boolean, default=True)
    crop_profile_id: Mapped[str] = mapped_column(ForeignKey("crop_profiles.id"))

    crop_profile: Mapped[CropProfile] = relationship()
    sensor_node: Mapped["SensorNode"] = relationship(back_populates="site", uselist=False)
    operators: Mapped[list[User]] = relationship(back_populates="site")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="site")


class SensorNode(Base):
    __tablename__ = "sensor_nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"), unique=True)
    connectivity: Mapped[str] = mapped_column(String(16), default="wifi")  # wifi | gsm
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    site: Mapped[Site] = relationship(back_populates="sensor_node")


class Reading(Base):
    """Time-series table. In production this is a TimescaleDB hypertable
    partitioned on ts; without the extension the composite index below
    serves the same per-site range queries."""

    __tablename__ = "readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"))
    node_id: Mapped[str] = mapped_column(ForeignKey("sensor_nodes.id"))
    parameter: Mapped[Parameter] = mapped_column(Enum(Parameter))
    value: Mapped[float] = mapped_column(Float)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    __table_args__ = (Index("ix_readings_site_param_ts", "site_id", "parameter", "ts"),)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"))
    parameter: Mapped[Parameter] = mapped_column(Enum(Parameter))
    state: Mapped[AlertState] = mapped_column(Enum(AlertState), default=AlertState.watch)
    severity: Mapped[str] = mapped_column(String(16), default="warning")  # warning | critical
    trigger_value: Mapped[float] = mapped_column(Float)
    band_min: Mapped[float] = mapped_column(Float)
    band_max: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    raised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)

    site: Mapped[Site] = relationship(back_populates="alerts")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="alert")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    alert_id: Mapped[str] = mapped_column(ForeignKey("alerts.id"))
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"))
    channel: Mapped[Channel] = mapped_column(Enum(Channel))
    recipient: Mapped[str] = mapped_column(String(128))  # username, email addr, or phone
    message: Mapped[str] = mapped_column(Text)
    # "delivered" for the real dashboard banner; "simulated" for the stubbed
    # email/SMS/USSD channels (no real provider is wired up — see notifier.py).
    status: Mapped[str] = mapped_column(String(16), default="simulated")
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    read: Mapped[bool] = mapped_column(Boolean, default=False)

    alert: Mapped[Alert] = relationship(back_populates="notifications")


class AuditLog(Base):
    """Append-only (FR 8.1). No update/delete endpoint exists for this table
    and none may be added — SRS business rule: 'No audit-log entries can be
    edited or deleted, not even by administrators.'"""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(128))  # username or "system"
    action: Mapped[str] = mapped_column(String(64), index=True)
    detail: Mapped[str] = mapped_column(Text)
    site_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

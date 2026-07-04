"""Append-only audit trail (FR 8.1).

Every reading, alert transition, notification dispatch, acknowledgement and
administrative action lands here. Write-only by design: there is no update
or delete path anywhere in the codebase, matching the SRS business rule
that audit entries are immutable even for administrators.
"""

from sqlalchemy.orm import Session

from .models import AuditLog


def log(db: Session, actor: str, action: str, detail: str, site_id: str | None = None) -> None:
    db.add(AuditLog(actor=actor, action=action, detail=detail, site_id=site_id))

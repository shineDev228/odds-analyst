"""Journal d'audit des actions sensibles."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.user import AuditLog


def record(
    db: Session,
    action: str,
    *,
    user_id: UUID | None = None,
    entity: str | None = None,
    entity_id: str | None = None,
    payload: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    entry = AuditLog(
        user_id=user_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        payload=payload,
        ip_address=request.client.host if request and request.client else None,
        created_at=datetime.now(UTC),
    )
    db.add(entry)
    db.commit()

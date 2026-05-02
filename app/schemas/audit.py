from datetime import datetime
from typing import Any

from app.schemas.common import ORMModel


class AuditLogResponse(ORMModel):
    id: int
    entity_type: str
    entity_id: int | None
    action: str
    actor: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    reason: str | None
    created_at: datetime

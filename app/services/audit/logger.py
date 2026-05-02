from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


class AuditLogger:
    """Writes AuditLog rows. Caller controls the surrounding transaction.

    Every auto-decision (classification persist, policy decision, reply
    draft, approve/reject/publish) must call this — blueprint §19, §24.
    """

    def __init__(self, db: AsyncSession, actor: str):
        self.db = db
        self.actor = actor

    async def record(
        self,
        *,
        entity_type: str,
        entity_id: int | None,
        action: str,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor=self.actor,
            before=before,
            after=after,
            reason=reason,
        )
        self.db.add(entry)
        return entry

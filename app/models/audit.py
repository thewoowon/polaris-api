from typing import Any

from sqlalchemy import Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditLog(Base):
    """Immutable trail of every automated decision and human override.

    Blueprint §19 + §24: all auto-decisions must leave a log; high-risk is
    default-deny; audit is non-negotiable.
    """

    __tablename__ = "audit_logs"

    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # "system", "user:<id>", or service name
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    before: Mapped[dict[str, Any] | None] = mapped_column("before", JSONB, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column("after", JSONB, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(512), nullable=True)

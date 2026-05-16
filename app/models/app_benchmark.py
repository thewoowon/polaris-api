import uuid
from typing import Any, TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.app_profile import AppProfile


class AppBenchmark(Base):
    __tablename__ = "app_benchmarks"

    id: Mapped[uuid.UUID] = mapped_column(  # type: ignore[assignment]
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    target_app_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competitor_app_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    period_start: Mapped[str] = mapped_column(Date, nullable=False)
    period_end: Mapped[str] = mapped_column(Date, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    comparison_summary: Mapped[str] = mapped_column(Text, nullable=False)

    target_app: Mapped["AppProfile"] = relationship(foreign_keys=[target_app_id])

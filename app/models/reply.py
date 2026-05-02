from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.review import Review


class ReplyTone(str, Enum):
    FORMAL = "formal"
    EMPATHETIC = "empathetic"
    BRIEF = "brief"


class ReplyStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"


class ReplyDraft(Base):
    __tablename__ = "reply_drafts"

    review_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    tone: Mapped[ReplyTone] = mapped_column(
        SqlEnum(ReplyTone, name="reply_tone", native_enum=False, length=16),
        nullable=False,
        default=ReplyTone.FORMAL,
    )
    template_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # list of kb_document ids or external doc refs used as grounding
    grounded_sources: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    generated_text: Mapped[str] = mapped_column(Text, nullable=False)
    requires_human_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[ReplyStatus] = mapped_column(
        SqlEnum(ReplyStatus, name="reply_status", native_enum=False, length=16),
        nullable=False,
        default=ReplyStatus.PENDING,
        index=True,
    )
    approved_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    review: Mapped["Review"] = relationship(back_populates="reply_draft")

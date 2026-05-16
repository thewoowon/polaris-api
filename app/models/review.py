import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.classification import ClassificationResult
    from app.models.policy import PolicyDecision
    from app.models.reply import ReplyDraft
    from app.models.app_profile import AppProfile


class ReviewSource(str, Enum):
    GOOGLE_PLAY = "google_play"
    APP_STORE = "app_store"
    INTERNAL = "internal"


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("source", "source_review_id", name="uq_review_source_pair"),
    )

    source: Mapped[ReviewSource] = mapped_column(
        SqlEnum(ReviewSource, name="review_source", native_enum=False, length=32),
        nullable=False,
        index=True,
    )
    source_review_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    app_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    os: Mapped[str | None] = mapped_column(String(32), nullable=True)
    locale: Mapped[str | None] = mapped_column(String(16), nullable=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    author_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    extra: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )
    app_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    classification: Mapped["ClassificationResult | None"] = relationship(
        back_populates="review", uselist=False, cascade="all, delete-orphan"
    )
    policy_decision: Mapped["PolicyDecision | None"] = relationship(
        back_populates="review", uselist=False, cascade="all, delete-orphan"
    )
    reply_draft: Mapped["ReplyDraft | None"] = relationship(
        back_populates="review", uselist=False, cascade="all, delete-orphan"
    )
    app_profile: Mapped["AppProfile | None"] = relationship(back_populates="reviews")

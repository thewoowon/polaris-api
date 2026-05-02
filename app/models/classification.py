from enum import Enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Enum as SqlEnum, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.review import Review


class ReviewCategory(str, Enum):
    BUG = "bug"
    PAYMENT = "payment"
    REFUND = "refund"
    PERFORMANCE = "performance"
    LOGIN_ACCOUNT = "login_account"
    UX_UI = "ux_ui"
    FEATURE_REQUEST = "feature_request"
    POLICY_INQUIRY = "policy_inquiry"
    COMPLAINT = "complaint"
    PRAISE = "praise"
    SPAM = "spam"
    OTHER = "other"


class Sentiment(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class Urgency(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ClassificationResult(Base):
    __tablename__ = "classification_results"

    review_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    # JSONB list of ReviewCategory values. Multi-label allowed (e.g. ['bug', 'payment']).
    categories: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    sentiment: Mapped[Sentiment] = mapped_column(
        SqlEnum(Sentiment, name="sentiment", native_enum=False, length=16), nullable=False
    )
    urgency: Mapped[Urgency] = mapped_column(
        SqlEnum(Urgency, name="urgency", native_enum=False, length=16), nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    entropy: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Normalized composite from blueprint §10.1; nullable so pre-feature rows
    # keep working until they're reclassified.
    ambiguity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # [{label: "bug", score: 0.72}, ...]
    top_candidates: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    needs_clarification: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    out_of_distribution: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)

    review: Mapped["Review"] = relationship(back_populates="classification")

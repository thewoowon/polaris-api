from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SqlEnum, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.review import Review


class PolicyAction(str, Enum):
    AUTO_REPLY = "auto_reply"
    DRAFT_REPLY = "draft_reply"
    REQUEST_CLARIFICATION = "request_clarification"
    ROUTE_TO_HUMAN = "route_to_human"
    CREATE_ISSUE = "create_issue"
    IGNORE = "ignore"


class PolicyDecision(Base):
    __tablename__ = "policy_decisions"

    review_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    action: Mapped[PolicyAction] = mapped_column(
        SqlEnum(PolicyAction, name="policy_action", native_enum=False, length=32),
        nullable=False,
        index=True,
    )
    risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reason_codes: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)

    review: Mapped["Review"] = relationship(back_populates="policy_decision")

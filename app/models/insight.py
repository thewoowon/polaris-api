import uuid
from enum import Enum
from typing import Any, TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.app_profile import AppProfile
    from app.models.company import Company


class InsightType(str, Enum):
    RISK = "risk"
    OPPORTUNITY = "opportunity"
    COMPETITIVE_GAP = "competitive_gap"
    UX_PROBLEM = "ux_problem"
    TECHNICAL_ISSUE = "technical_issue"
    OPERATION_ISSUE = "operation_issue"
    CUSTOMER_SUPPORT_ISSUE = "customer_support_issue"


class InsightSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class BusinessImpact(str, Enum):
    RETENTION = "retention"
    CONVERSION = "conversion"
    TRUST = "trust"
    BRAND = "brand"
    COST = "cost"
    COMPLIANCE = "compliance"
    UNKNOWN = "unknown"


class Insight(Base):
    __tablename__ = "insights"

    id: Mapped[uuid.UUID] = mapped_column(  # type: ignore[assignment]
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    app_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    insight_type: Mapped[InsightType] = mapped_column(
        SqlEnum(InsightType, name="insight_type_enum", native_enum=False, length=32),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_review_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    severity: Mapped[InsightSeverity] = mapped_column(
        SqlEnum(InsightSeverity, name="insight_severity_enum", native_enum=False, length=16),
        nullable=False,
    )
    business_impact: Mapped[BusinessImpact] = mapped_column(
        SqlEnum(BusinessImpact, name="insight_business_impact_enum", native_enum=False, length=32),
        nullable=False,
    )
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)

    app_profile: Mapped["AppProfile"] = relationship(back_populates="insights")
    company: Mapped["Company"] = relationship()

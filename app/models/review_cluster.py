import uuid
from enum import Enum
from typing import Any, TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.app_profile import AppProfile


class IssueType(str, Enum):
    UX = "ux"
    BUG = "bug"
    PERFORMANCE = "performance"
    POLICY = "policy"
    OPERATION = "operation"
    CUSTOMER_SUPPORT = "customer_support"
    PRICING = "pricing"
    SECURITY = "security"
    AUTHENTICATION = "authentication"
    UNKNOWN = "unknown"


class ClusterSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReviewCluster(Base):
    __tablename__ = "review_clusters"

    id: Mapped[uuid.UUID] = mapped_column(  # type: ignore[assignment]
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    app_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    issue_type: Mapped[IssueType] = mapped_column(
        SqlEnum(IssueType, name="cluster_issue_type", native_enum=False, length=32),
        nullable=False,
    )
    review_count: Mapped[int] = mapped_column(Integer, nullable=False)
    negative_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    average_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity: Mapped[ClusterSeverity] = mapped_column(
        SqlEnum(ClusterSeverity, name="cluster_severity", native_enum=False, length=16),
        nullable=False,
    )
    representative_review_ids: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )

    app_profile: Mapped["AppProfile"] = relationship(back_populates="clusters")

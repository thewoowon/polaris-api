import uuid
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.app_profile import AppProfile


class ReportType(str, Enum):
    COMPANY_APP_REVIEW = "company_app_review"
    COMPETITIVE_BENCHMARK = "competitive_benchmark"
    MONTHLY_VOC = "monthly_voc"
    SALES_OUTBOUND = "sales_outbound"


class ReportStatus(str, Enum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    EXPORTED = "exported"
    SENT = "sent"


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(  # type: ignore[assignment]
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    app_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    report_type: Mapped[ReportType] = mapped_column(
        SqlEnum(ReportType, name="report_type_enum", native_enum=False, length=32),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    period_start: Mapped[str] = mapped_column(String(16), nullable=False)
    period_end: Mapped[str] = mapped_column(String(16), nullable=False)
    markdown_content: Mapped[str] = mapped_column(Text, nullable=False)
    executive_summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        SqlEnum(ReportStatus, name="report_status_enum", native_enum=False, length=16),
        nullable=False,
        server_default="draft",
    )

    company: Mapped["Company"] = relationship(back_populates="reports")
    app_profile: Mapped["AppProfile | None"] = relationship(back_populates="reports")

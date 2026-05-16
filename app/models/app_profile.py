import uuid
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.review import Review
    from app.models.review_cluster import ReviewCluster
    from app.models.insight import Insight
    from app.models.report import Report


class Platform(str, Enum):
    IOS = "ios"
    ANDROID = "android"
    BOTH = "both"


class AppProfile(Base):
    __tablename__ = "app_profiles"

    id: Mapped[uuid.UUID] = mapped_column(  # type: ignore[assignment]
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    app_name: Mapped[str] = mapped_column(String(256), nullable=False)
    platform: Mapped[Platform] = mapped_column(
        SqlEnum(Platform, name="app_platform", native_enum=False, length=16),
        nullable=False,
    )
    app_store_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    play_store_package: Mapped[str | None] = mapped_column(String(256), nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    country: Mapped[str] = mapped_column(String(8), nullable=False, server_default="kr")
    is_target: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_competitor: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    company: Mapped["Company"] = relationship(back_populates="apps")
    reviews: Mapped[list["Review"]] = relationship(back_populates="app_profile")
    clusters: Mapped[list["ReviewCluster"]] = relationship(
        back_populates="app_profile", cascade="all, delete-orphan"
    )
    insights: Mapped[list["Insight"]] = relationship(
        back_populates="app_profile", cascade="all, delete-orphan"
    )
    reports: Mapped[list["Report"]] = relationship(back_populates="app_profile")

import uuid
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.app_profile import AppProfile
    from app.models.report import Report


class Industry(str, Enum):
    FINANCE = "finance"
    FINTECH = "fintech"
    COMMERCE = "commerce"
    DELIVERY = "delivery"
    PUBLIC = "public"
    EDUCATION = "education"
    MOBILITY = "mobility"
    ENTERTAINMENT = "entertainment"
    OTHER = "other"


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(  # type: ignore[assignment]
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    industry: Mapped[Industry] = mapped_column(
        SqlEnum(Industry, name="company_industry", native_enum=False, length=32),
        nullable=False,
    )
    homepage_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(256), nullable=True)
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)

    apps: Mapped[list["AppProfile"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    reports: Mapped[list["Report"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )

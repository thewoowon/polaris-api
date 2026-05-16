"""UUID primary-key mixin for Phase 2 domain models.

Use together with the existing Base so all tables share one metadata:

    class Company(UUIDMixin, Base):
        __tablename__ = "companies"
        ...
"""

import uuid

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )

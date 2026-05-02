from enum import Enum

from sqlalchemy import Boolean, Enum as SqlEnum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DocType(str, Enum):
    FAQ = "faq"
    RELEASE_NOTE = "release_note"
    ANNOUNCEMENT = "announcement"
    INCIDENT_RESPONSE = "incident_response"
    CS_POLICY = "cs_policy"
    FORBIDDEN_EXPRESSION = "forbidden_expression"


class KbDocument(Base):
    __tablename__ = "kb_documents"

    title: Mapped[str] = mapped_column(String(256), nullable=False)
    doc_type: Mapped[DocType] = mapped_column(
        SqlEnum(DocType, name="kb_doc_type", native_enum=False, length=32),
        nullable=False,
        index=True,
    )
    tags: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true", index=True
    )

    chunks: Mapped[list["KbChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class KbChunk(Base):
    __tablename__ = "kb_chunks"

    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("kb_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Embedding column deferred until pgvector lands (blueprint §12.3 Phase-3).
    # Add `embedding: Mapped[Any] = mapped_column(Vector(1536), ...)` then.
    chunk_metadata: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    document: Mapped["KbDocument"] = relationship(back_populates="chunks")

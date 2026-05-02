from datetime import datetime

from pydantic import BaseModel, Field

from app.models.kb import DocType
from app.schemas.common import ORMModel


class KbDocumentCreate(BaseModel):
    title: str
    doc_type: DocType
    content: str
    tags: list[str] = Field(default_factory=list)
    active: bool = True


class KbDocumentUpdate(BaseModel):
    """Partial update — all fields optional, unset fields stay untouched."""

    title: str | None = None
    doc_type: DocType | None = None
    content: str | None = None
    tags: list[str] | None = None
    active: bool | None = None


class KbDocumentResponse(ORMModel):
    id: int
    title: str
    doc_type: DocType
    tags: list[str]
    content: str
    version: int
    active: bool
    created_at: datetime
    updated_at: datetime


class KbSearchRequest(BaseModel):
    query: str
    top_k: int = Field(5, ge=1, le=50)
    doc_types: list[DocType] | None = None


class KbSearchHit(BaseModel):
    document_id: int
    chunk_id: int | None = None
    title: str
    doc_type: DocType
    score: float
    snippet: str

import uuid
from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.models.review import ReviewSource


class IngestionItem(BaseModel):
    """Shape a source produces; the scheduler persists it as a Review."""

    source: ReviewSource
    source_review_id: str | None = None
    app_version: str | None = None
    os: str | None = None
    locale: str | None = None
    rating: int | None = Field(None, ge=1, le=5)
    author_name: str | None = None
    raw_text: str
    extra: dict[str, Any] = Field(default_factory=dict)
    app_id: uuid.UUID | None = None


class ReviewSourceProto(Protocol):
    """A pluggable review source. Stateless impls are preferred — the
    scheduler recreates nothing between ticks so sources that need cursors
    should persist their own state.
    """

    name: str

    async def fetch(self) -> list[IngestionItem]: ...

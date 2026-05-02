from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.review import ReviewSource
from app.schemas.classification import ClassificationResponse
from app.schemas.common import ORMModel
from app.schemas.policy import PolicyDecisionResponse
from app.schemas.reply import ReplyDraftResponse


class ReviewIngest(BaseModel):
    source: ReviewSource
    source_review_id: str | None = None
    app_version: str | None = None
    os: str | None = None
    locale: str | None = None
    rating: int | None = Field(None, ge=1, le=5)
    author_name: str | None = None
    raw_text: str
    normalized_text: str | None = None  # if omitted, backend normalizes from raw_text
    extra: dict[str, Any] = Field(default_factory=dict)


class ReviewBulkIngest(BaseModel):
    reviews: list[ReviewIngest]


class ReviewResponse(ORMModel):
    id: int
    source: ReviewSource
    source_review_id: str | None
    app_version: str | None
    os: str | None
    locale: str | None
    rating: int | None
    author_name: str | None
    raw_text: str
    normalized_text: str
    ingested_at: datetime
    created_at: datetime
    updated_at: datetime
    extra: dict[str, Any] = Field(default_factory=dict)


class ReviewDetailResponse(ReviewResponse):
    classification: ClassificationResponse | None = None
    policy_decision: PolicyDecisionResponse | None = None
    reply_draft: ReplyDraftResponse | None = None

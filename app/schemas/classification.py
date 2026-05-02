from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.classification import ReviewCategory, Sentiment, Urgency
from app.schemas.common import ORMModel


class TopCandidate(BaseModel):
    label: str
    score: float = Field(..., ge=0.0, le=1.0)


class ClassificationPayload(BaseModel):
    """Structured output produced by the classifier service (LLM or model)."""

    categories: list[ReviewCategory]
    sentiment: Sentiment
    urgency: Urgency
    confidence: float = Field(..., ge=0.0, le=1.0)
    entropy: float | None = None
    ambiguity_score: float | None = None
    top_candidates: list[TopCandidate] | None = None
    needs_clarification: bool = False
    out_of_distribution: bool = False
    model_version: str


class ClarifyRequest(BaseModel):
    """Operator-driven override after a REQUEST_CLARIFICATION decision."""

    categories: list[ReviewCategory] = Field(..., min_length=1)
    reason: str | None = Field(None, max_length=500)


class ShadowCompareResponse(BaseModel):
    """Side-by-side classifier output for shadow / A-B evaluation.

    Neither result is persisted — diagnostic only (blueprint §18.1 shadow
    mode: produce classifications internally without affecting operations).
    """

    stub: ClassificationPayload
    llm: ClassificationPayload | None = None
    llm_error: str | None = None


class ClassificationResponse(ORMModel):
    id: int
    review_id: int
    categories: list[str]
    sentiment: Sentiment
    urgency: Urgency
    confidence: float
    entropy: float | None
    ambiguity_score: float | None
    top_candidates: list[dict[str, Any]] | None
    needs_clarification: bool
    out_of_distribution: bool
    model_version: str
    created_at: datetime
    updated_at: datetime

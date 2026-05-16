import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class BenchmarkRequest(BaseModel):
    target_app_id: uuid.UUID
    competitor_app_ids: list[uuid.UUID] = Field(..., min_length=1)
    period_start: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    period_end: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")


class BenchmarkMetrics(BaseModel):
    review_count: int
    average_rating: float
    negative_ratio: float
    critical_issue_count: int
    top_negative_categories: list[str]
    response_rate: float | None = None


class AppBenchmarkResponse(ORMModel):
    id: uuid.UUID
    target_app_id: uuid.UUID
    competitor_app_ids: list[Any]
    period_start: str
    period_end: str
    metrics: dict[str, Any]
    comparison_summary: str
    created_at: datetime
    updated_at: datetime

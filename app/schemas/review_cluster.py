import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.models.review_cluster import ClusterSeverity, IssueType
from app.schemas.common import ORMModel


class ReviewClusterResponse(ORMModel):
    id: uuid.UUID
    app_id: uuid.UUID
    title: str
    summary: str
    issue_type: IssueType
    review_count: int
    negative_ratio: float
    average_rating: float | None
    severity: ClusterSeverity
    representative_review_ids: list[Any] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.models.insight import BusinessImpact, InsightSeverity, InsightType
from app.schemas.common import ORMModel


class InsightResponse(ORMModel):
    id: uuid.UUID
    app_id: uuid.UUID
    company_id: uuid.UUID
    insight_type: InsightType
    title: str
    summary: str
    evidence_review_ids: list[Any] = Field(default_factory=list)
    severity: InsightSeverity
    business_impact: BusinessImpact
    recommended_action: str
    created_at: datetime
    updated_at: datetime

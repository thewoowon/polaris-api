from datetime import datetime

from pydantic import BaseModel, Field

from app.models.policy import PolicyAction
from app.schemas.common import ORMModel


class PolicyEvaluateResult(BaseModel):
    """Structured output of the policy engine before persistence."""

    action: PolicyAction
    risk_score: float = Field(..., ge=0.0, le=1.0)
    reason_codes: list[str]
    policy_version: str


class PolicyDecisionResponse(ORMModel):
    id: int
    review_id: int
    action: PolicyAction
    risk_score: float
    reason_codes: list[str]
    policy_version: str
    created_at: datetime
    updated_at: datetime

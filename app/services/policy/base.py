from typing import Protocol

from app.schemas.classification import ClassificationPayload
from app.schemas.policy import PolicyEvaluateResult


class PolicyContext(Protocol):
    rating: int | None
    app_version: str | None


class PolicyEngine(Protocol):
    policy_version: str

    async def evaluate(
        self,
        *,
        classification: ClassificationPayload,
        rating: int | None = None,
        app_version: str | None = None,
    ) -> PolicyEvaluateResult: ...

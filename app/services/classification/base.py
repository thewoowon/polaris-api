from typing import Protocol

from app.schemas.classification import ClassificationPayload


class Classifier(Protocol):
    """Contract every classifier impl must honour.

    Blueprint §17 — initial MVP uses Option A (LLM structured output), later
    moves to Option B (light model + rules) or hybrid. The service layer
    hides that choice from the rest of the app.
    """

    model_version: str

    async def classify(
        self, *, review_text: str, review_id: int | None = None
    ) -> ClassificationPayload: ...

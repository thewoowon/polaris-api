from datetime import datetime

from app.models.policy import PolicyAction
from app.models.reply import ReplyStatus
from app.models.review import ReviewSource
from app.schemas.common import ORMModel


class QueueItem(ORMModel):
    review_id: int
    source: ReviewSource
    rating: int | None
    snippet: str
    created_at: datetime
    ingested_at: datetime
    category: str | None
    action: PolicyAction
    risk_score: float
    reason_codes: list[str]
    draft_status: ReplyStatus | None

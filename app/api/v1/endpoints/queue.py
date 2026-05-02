from fastapi import APIRouter, Depends, Query
from sqlalchemy import cast, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.classification import ClassificationResult
from app.models.policy import PolicyAction, PolicyDecision
from app.models.reply import ReplyDraft, ReplyStatus
from app.models.review import Review
from app.schemas.common import Page
from app.schemas.queue import QueueItem

router = APIRouter()

# Actions that require human attention (blueprint §9).
HUMAN_ACTIONS = (PolicyAction.ROUTE_TO_HUMAN, PolicyAction.CREATE_ISSUE)

# Drafts that are still open; published/rejected are finalized and leave the queue.
OPEN_DRAFT_STATUSES = (ReplyStatus.PENDING, ReplyStatus.APPROVED)

SNIPPET_CHARS = 140


def _snippet(text: str) -> str:
    if len(text) <= SNIPPET_CHARS:
        return text
    return text[: SNIPPET_CHARS - 1].rstrip() + "…"


@router.get("", response_model=Page[QueueItem])
async def list_queue(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> Page[QueueItem]:
    first_cat = func.jsonb_extract_path_text(
        cast(ClassificationResult.categories, JSONB), "0"
    ).label("category")

    # Shared WHERE: human-review action + draft is either absent or still open.
    open_filter = or_(
        ReplyDraft.status.is_(None),
        ReplyDraft.status.in_(OPEN_DRAFT_STATUSES),
    )
    action_filter = PolicyDecision.action.in_(HUMAN_ACTIONS)

    count_stmt = (
        select(func.count())
        .select_from(Review)
        .join(PolicyDecision, PolicyDecision.review_id == Review.id)
        .outerjoin(ReplyDraft, ReplyDraft.review_id == Review.id)
        .where(action_filter, open_filter)
    )
    total = (await db.execute(count_stmt)).scalar_one() or 0

    stmt = (
        select(
            Review.id.label("review_id"),
            Review.source,
            Review.rating,
            Review.normalized_text,
            Review.created_at,
            Review.ingested_at,
            first_cat,
            PolicyDecision.action,
            PolicyDecision.risk_score,
            PolicyDecision.reason_codes,
            ReplyDraft.status.label("draft_status"),
        )
        .select_from(Review)
        .join(PolicyDecision, PolicyDecision.review_id == Review.id)
        .outerjoin(ClassificationResult, ClassificationResult.review_id == Review.id)
        .outerjoin(ReplyDraft, ReplyDraft.review_id == Review.id)
        .where(action_filter, open_filter)
        # SLA-oriented: highest risk first, then oldest first within the same risk.
        .order_by(PolicyDecision.risk_score.desc(), Review.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).all()

    items = [
        QueueItem(
            review_id=r.review_id,
            source=r.source,
            rating=r.rating,
            snippet=_snippet(r.normalized_text),
            created_at=r.created_at,
            ingested_at=r.ingested_at,
            category=r.category,
            action=r.action,
            risk_score=r.risk_score,
            reason_codes=r.reason_codes or [],
            draft_status=r.draft_status,
        )
        for r in rows
    ]

    return Page[QueueItem](items=items, total=total, limit=limit, offset=offset)

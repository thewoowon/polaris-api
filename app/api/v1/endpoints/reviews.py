from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, cast, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import get_db
from app.models.audit import AuditLog
from app.models.classification import ClassificationResult, ReviewCategory, Sentiment
from app.models.policy import PolicyAction, PolicyDecision
from app.models.reply import ReplyDraft
from app.models.review import Review, ReviewSource
from app.schemas.audit import AuditLogResponse
from app.schemas.common import Page
from app.schemas.review import (
    ReviewBulkIngest,
    ReviewDetailResponse,
    ReviewIngest,
    ReviewResponse,
)
from app.services.audit.logger import AuditLogger
from app.services.normalization import normalize_text
from app.services.registry import get_audit_logger

router = APIRouter()


def _build_review(payload: ReviewIngest) -> Review:
    return Review(
        source=payload.source,
        source_review_id=payload.source_review_id,
        app_version=payload.app_version,
        os=payload.os,
        locale=payload.locale,
        rating=payload.rating,
        author_name=payload.author_name,
        raw_text=payload.raw_text,
        normalized_text=payload.normalized_text or normalize_text(payload.raw_text),
        extra=payload.extra,
    )


@router.post("/ingest", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
async def ingest(
    payload: ReviewIngest,
    db: AsyncSession = Depends(get_db),
    audit: AuditLogger = Depends(get_audit_logger),
) -> Review:
    review = _build_review(payload)
    db.add(review)
    await db.flush()
    await audit.record(
        entity_type="review",
        entity_id=review.id,
        action="ingest",
        after={
            "source": payload.source.value,
            "source_review_id": payload.source_review_id,
        },
    )
    await db.commit()
    await db.refresh(review)
    return review


@router.post("/bulk-ingest", response_model=list[ReviewResponse], status_code=status.HTTP_201_CREATED)
async def bulk_ingest(
    payload: ReviewBulkIngest,
    db: AsyncSession = Depends(get_db),
    audit: AuditLogger = Depends(get_audit_logger),
) -> list[Review]:
    created = [_build_review(item) for item in payload.reviews]
    for r in created:
        db.add(r)
    await db.flush()
    for r in created:
        await audit.record(entity_type="review", entity_id=r.id, action="bulk_ingest")
    await db.commit()
    for r in created:
        await db.refresh(r)
    return created


@router.get("", response_model=Page[ReviewResponse])
async def list_reviews(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    source: ReviewSource | None = Query(None),
    sentiment: Sentiment | None = Query(None),
    action: PolicyAction | None = Query(None),
    category: ReviewCategory | None = Query(None),
    rating_min: int | None = Query(None, ge=1, le=5),
    rating_max: int | None = Query(None, ge=1, le=5),
    q: str | None = Query(None, description="ILIKE match on raw_text + normalized_text"),
    db: AsyncSession = Depends(get_db),
) -> Page[ReviewResponse]:
    base = select(Review)
    count_base = select(func.count()).select_from(Review)

    # Review-only filters.
    if source:
        base = base.where(Review.source == source)
        count_base = count_base.where(Review.source == source)
    if rating_min is not None:
        base = base.where(Review.rating >= rating_min)
        count_base = count_base.where(Review.rating >= rating_min)
    if rating_max is not None:
        base = base.where(Review.rating <= rating_max)
        count_base = count_base.where(Review.rating <= rating_max)
    if q:
        pattern = f"%{q}%"
        text_filter = or_(
            Review.raw_text.ilike(pattern),
            Review.normalized_text.ilike(pattern),
        )
        base = base.where(text_filter)
        count_base = count_base.where(text_filter)

    # Classification join (sentiment + category).
    if sentiment or category:
        base = base.join(ClassificationResult, ClassificationResult.review_id == Review.id)
        count_base = count_base.join(
            ClassificationResult, ClassificationResult.review_id == Review.id
        )
        if sentiment:
            base = base.where(ClassificationResult.sentiment == sentiment)
            count_base = count_base.where(ClassificationResult.sentiment == sentiment)
        if category:
            # JSONB `@>` containment: categories array includes this value.
            contains_clause = ClassificationResult.categories.op("@>")(
                cast([category.value], JSONB)
            )
            base = base.where(contains_clause)
            count_base = count_base.where(contains_clause)

    # Policy join (action).
    if action:
        base = base.join(PolicyDecision, PolicyDecision.review_id == Review.id)
        count_base = count_base.join(
            PolicyDecision, PolicyDecision.review_id == Review.id
        )
        base = base.where(PolicyDecision.action == action)
        count_base = count_base.where(PolicyDecision.action == action)

    total = (await db.execute(count_base)).scalar_one() or 0
    rows = (
        await db.execute(
            base.order_by(Review.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()
    return Page[ReviewResponse](
        items=[ReviewResponse.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{review_id}/audit", response_model=list[AuditLogResponse])
async def review_audit(
    review_id: int, db: AsyncSession = Depends(get_db)
) -> list[AuditLog]:
    """All audit rows that relate to this review's pipeline.

    Audit rows are keyed by (entity_type, entity_id) where entity_id is the
    row id of the owning table, not the review_id. So we resolve the related
    rows first, then union their audit trails sorted by time.
    """
    review = (
        await db.execute(select(Review).where(Review.id == review_id))
    ).scalar_one_or_none()
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")

    classif = (
        await db.execute(
            select(ClassificationResult).where(ClassificationResult.review_id == review_id)
        )
    ).scalar_one_or_none()
    policy = (
        await db.execute(
            select(PolicyDecision).where(PolicyDecision.review_id == review_id)
        )
    ).scalar_one_or_none()
    draft = (
        await db.execute(select(ReplyDraft).where(ReplyDraft.review_id == review_id))
    ).scalar_one_or_none()

    conditions = [
        and_(AuditLog.entity_type == "review", AuditLog.entity_id == review.id),
    ]
    if classif:
        conditions.append(
            and_(
                AuditLog.entity_type == "classification_result",
                AuditLog.entity_id == classif.id,
            )
        )
    if policy:
        conditions.append(
            and_(
                AuditLog.entity_type == "policy_decision",
                AuditLog.entity_id == policy.id,
            )
        )
    if draft:
        conditions.append(
            and_(AuditLog.entity_type == "reply_draft", AuditLog.entity_id == draft.id)
        )

    rows = (
        await db.execute(
            select(AuditLog)
            .where(or_(*conditions))
            .order_by(AuditLog.created_at.asc())
        )
    ).scalars().all()
    return rows


@router.get("/{review_id}", response_model=ReviewDetailResponse)
async def get_review(
    review_id: int, db: AsyncSession = Depends(get_db)
) -> ReviewDetailResponse:
    result = await db.execute(
        select(Review)
        .where(Review.id == review_id)
        .options(
            selectinload(Review.classification),
            selectinload(Review.policy_decision),
            selectinload(Review.reply_draft),
        )
    )
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="review not found")
    return ReviewDetailResponse.model_validate(review)

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import cast, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.classification import ClassificationResult, Sentiment
from app.models.policy import PolicyAction, PolicyDecision
from app.models.reply import ReplyDraft, ReplyStatus
from app.models.review import Review
from app.schemas.dashboard import (
    CategoryBreakdown,
    DashboardSummary,
    HighRiskItem,
    TrendPoint,
)

router = APIRouter()

HIGH_RISK_ACTIONS = (PolicyAction.ROUTE_TO_HUMAN, PolicyAction.CREATE_ISSUE)


@router.get("/summary", response_model=DashboardSummary)
async def summary(db: AsyncSession = Depends(get_db)) -> DashboardSummary:
    total = (await db.execute(select(func.count()).select_from(Review))).scalar_one() or 0
    negative = (
        await db.execute(
            select(func.count())
            .select_from(ClassificationResult)
            .where(ClassificationResult.sentiment == Sentiment.NEGATIVE)
        )
    ).scalar_one() or 0
    auto_replies = (
        await db.execute(
            select(func.count())
            .select_from(PolicyDecision)
            .where(PolicyDecision.action == PolicyAction.AUTO_REPLY)
        )
    ).scalar_one() or 0
    human_reviews = (
        await db.execute(
            select(func.count())
            .select_from(PolicyDecision)
            .where(PolicyDecision.action.in_(HIGH_RISK_ACTIONS))
        )
    ).scalar_one() or 0
    high_risk = (
        await db.execute(
            select(func.count())
            .select_from(PolicyDecision)
            .where(PolicyDecision.risk_score >= 0.7)
        )
    ).scalar_one() or 0

    def ratio(n: int) -> float:
        return round(n / total, 4) if total else 0.0

    return DashboardSummary(
        total_reviews=total,
        negative_ratio=ratio(negative),
        auto_reply_rate=ratio(auto_replies),
        human_review_rate=ratio(human_reviews),
        high_risk_count=high_risk,
    )


@router.get("/trends", response_model=list[TrendPoint])
async def trends(
    days: int = Query(14, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
) -> list[TrendPoint]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    day_col = func.date_trunc("day", Review.created_at).label("day")
    neg = func.count(ClassificationResult.id).filter(
        ClassificationResult.sentiment == Sentiment.NEGATIVE
    )
    stmt = (
        select(day_col, func.count(Review.id).label("total"), neg.label("neg"))
        .select_from(Review)
        .outerjoin(ClassificationResult, ClassificationResult.review_id == Review.id)
        .where(Review.created_at >= since)
        .group_by(day_col)
        .order_by(day_col)
    )
    rows = (await db.execute(stmt)).all()
    return [
        TrendPoint(day=r.day.date() if hasattr(r.day, "date") else r.day, total=r.total, negative=r.neg)
        for r in rows
    ]


@router.get("/categories", response_model=list[CategoryBreakdown])
async def categories(db: AsyncSession = Depends(get_db)) -> list[CategoryBreakdown]:
    # jsonb_array_elements_text unpacks the categories array column.
    element = func.jsonb_array_elements_text(
        cast(ClassificationResult.categories, JSONB)
    ).label("category")
    stmt = select(element, func.count().label("count")).group_by(element).order_by(func.count().desc())
    rows = (await db.execute(stmt)).all()
    total = sum(r.count for r in rows) or 1
    return [
        CategoryBreakdown(category=r.category, count=r.count, share=round(r.count / total, 4))
        for r in rows
    ]


@router.get("/high-risk", response_model=list[HighRiskItem])
async def high_risk(
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[HighRiskItem]:
    # Take only the first category from the JSONB array — otherwise a
    # multi-labelled review yields one row per category and explodes the list.
    first_cat = func.jsonb_extract_path_text(
        cast(ClassificationResult.categories, JSONB), "0"
    ).label("category")
    stmt = (
        select(
            PolicyDecision.review_id,
            PolicyDecision.action,
            PolicyDecision.risk_score,
            first_cat,
            PolicyDecision.created_at,
        )
        .join(Review, Review.id == PolicyDecision.review_id)
        .outerjoin(ClassificationResult, ClassificationResult.review_id == Review.id)
        .where(PolicyDecision.risk_score >= 0.6)
        .order_by(PolicyDecision.risk_score.desc(), PolicyDecision.created_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [
        HighRiskItem(
            review_id=r.review_id,
            action=r.action.value if hasattr(r.action, "value") else str(r.action),
            risk_score=r.risk_score,
            category=r.category or "unknown",
            created_at=r.created_at.isoformat() if isinstance(r.created_at, datetime) else str(r.created_at),
        )
        for r in rows
    ]

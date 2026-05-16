"""App-level review analysis: summary stats and time-series trends."""

import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.classification import ClassificationResult, Sentiment
from app.models.review import Review


class AnalysisService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def summary(self, app_id: uuid.UUID) -> dict:
        result = await self._db.execute(
            select(
                func.count(Review.id),
                func.avg(Review.rating),
                func.min(Review.ingested_at),
                func.max(Review.ingested_at),
            ).where(Review.app_id == app_id)
        )
        row = result.one()
        total = row[0] or 0
        avg_rating = round(float(row[1]), 2) if row[1] else None
        first_at = row[2]
        last_at = row[3]

        # Negative ratio (rating <= 2)
        neg_result = await self._db.execute(
            select(func.count(Review.id)).where(Review.app_id == app_id, Review.rating <= 2)
        )
        neg_count = neg_result.scalar_one() or 0
        negative_ratio = round(neg_count / total, 3) if total > 0 else 0.0

        # Critical count (rating == 1)
        crit_result = await self._db.execute(
            select(func.count(Review.id)).where(Review.app_id == app_id, Review.rating == 1)
        )
        critical_count = crit_result.scalar_one() or 0

        # Rating distribution
        rating_dist_result = await self._db.execute(
            select(Review.rating, func.count(Review.id))
            .where(Review.app_id == app_id, Review.rating.isnot(None))
            .group_by(Review.rating)
            .order_by(Review.rating)
        )
        rating_distribution = {str(r): c for r, c in rating_dist_result.all()}

        # Category distribution from classifications
        cls_rows = await self._db.execute(
            select(ClassificationResult.categories)
            .join(Review, Review.id == ClassificationResult.review_id)
            .where(Review.app_id == app_id)
        )
        category_counter: Counter = Counter()
        for (cats,) in cls_rows.all():
            if cats:
                category_counter.update(cats)
        top_categories = [
            {"category": cat, "count": cnt}
            for cat, cnt in category_counter.most_common(10)
        ]

        # Sentiment distribution
        sentiment_rows = await self._db.execute(
            select(ClassificationResult.sentiment, func.count())
            .join(Review, Review.id == ClassificationResult.review_id)
            .where(Review.app_id == app_id)
            .group_by(ClassificationResult.sentiment)
        )
        sentiment_distribution = {s: c for s, c in sentiment_rows.all()}

        # Recent 7-day review count
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        recent_result = await self._db.execute(
            select(func.count(Review.id)).where(
                Review.app_id == app_id,
                Review.ingested_at >= seven_days_ago,
            )
        )
        recent_count = recent_result.scalar_one() or 0

        return {
            "app_id": str(app_id),
            "total_reviews": total,
            "average_rating": avg_rating,
            "negative_ratio": negative_ratio,
            "critical_count": critical_count,
            "recent_7d_count": recent_count,
            "first_review_at": first_at.isoformat() if first_at else None,
            "last_review_at": last_at.isoformat() if last_at else None,
            "rating_distribution": rating_distribution,
            "top_categories": top_categories,
            "sentiment_distribution": sentiment_distribution,
        }

    async def trends(self, app_id: uuid.UUID, days: int = 30) -> dict:
        since = datetime.now(timezone.utc) - timedelta(days=days)

        rows = await self._db.execute(
            select(
                func.date_trunc("day", Review.ingested_at).label("day"),
                func.count(Review.id).label("count"),
                func.avg(Review.rating).label("avg_rating"),
            )
            .where(Review.app_id == app_id, Review.ingested_at >= since)
            .group_by(func.date_trunc("day", Review.ingested_at))
            .order_by(func.date_trunc("day", Review.ingested_at))
        )

        daily = [
            {
                "date": row.day.date().isoformat(),
                "count": row.count,
                "avg_rating": round(float(row.avg_rating), 2) if row.avg_rating else None,
            }
            for row in rows.all()
        ]

        # Negative ratio per day
        neg_rows = await self._db.execute(
            select(
                func.date_trunc("day", Review.ingested_at).label("day"),
                func.count(Review.id).label("neg_count"),
            )
            .where(Review.app_id == app_id, Review.ingested_at >= since, Review.rating <= 2)
            .group_by(func.date_trunc("day", Review.ingested_at))
        )
        neg_by_day = {row.day.date().isoformat(): row.neg_count for row in neg_rows.all()}

        for d in daily:
            total_day = d["count"]
            neg_day = neg_by_day.get(d["date"], 0)
            d["negative_ratio"] = round(neg_day / total_day, 3) if total_day > 0 else 0.0

        return {
            "app_id": str(app_id),
            "period_days": days,
            "daily": daily,
        }

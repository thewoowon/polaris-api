"""Compare a target app vs. competitors using stored review stats."""

from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_benchmark import AppBenchmark
from app.models.app_profile import AppProfile
from app.models.classification import ClassificationResult
from app.models.review import Review
from app.models.review_cluster import ClusterSeverity, ReviewCluster
from app.schemas.app_benchmark import BenchmarkRequest


async def _compute_metrics(
    app_id,
    period_start: str,
    period_end: str,
    db: AsyncSession,
) -> dict:
    start_dt = datetime.strptime(period_start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_dt = datetime.strptime(period_end, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    base = select(Review).where(
        Review.app_id == app_id,
        Review.ingested_at >= start_dt,
        Review.ingested_at <= end_dt,
    )

    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    review_count = count_result.scalar_one() or 0

    if review_count == 0:
        # No reviews in period — fall back to all-time
        base = select(Review).where(Review.app_id == app_id)
        count_result = await db.execute(select(func.count()).select_from(base.subquery()))
        review_count = count_result.scalar_one() or 0

    stat_result = await db.execute(
        select(func.avg(Review.rating)).select_from(base.subquery())
    )
    avg_rating = float(stat_result.scalar_one() or 0)

    neg_result = await db.execute(
        select(func.count()).select_from(
            base.where(Review.rating <= 2).subquery()
        )
    )
    neg_count = neg_result.scalar_one() or 0
    negative_ratio = round(neg_count / review_count, 3) if review_count else 0.0

    # Critical cluster count
    crit_result = await db.execute(
        select(func.count(ReviewCluster.id)).where(
            ReviewCluster.app_id == app_id,
            ReviewCluster.severity == ClusterSeverity.CRITICAL,
        )
    )
    critical_issue_count = crit_result.scalar_one() or 0

    # Top negative categories
    cls_rows = await db.execute(
        select(ClassificationResult.categories)
        .join(Review, Review.id == ClassificationResult.review_id)
        .where(Review.app_id == app_id, Review.rating <= 2)
    )
    from collections import Counter
    cat_counter: Counter = Counter()
    for (cats,) in cls_rows.all():
        if cats:
            cat_counter.update(cats)
    top_negative_categories = [c for c, _ in cat_counter.most_common(5)]

    return {
        "review_count": review_count,
        "average_rating": round(avg_rating, 2),
        "negative_ratio": negative_ratio,
        "critical_issue_count": critical_issue_count,
        "top_negative_categories": top_negative_categories,
    }


class BenchmarkService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def run(self, req: BenchmarkRequest) -> AppBenchmark:
        target_metrics = await _compute_metrics(
            req.target_app_id, req.period_start, req.period_end, self._db
        )

        all_metrics: dict = {"target": {"app_id": str(req.target_app_id), **target_metrics}}
        competitors_data = []

        for cid in req.competitor_app_ids:
            cm = await _compute_metrics(cid, req.period_start, req.period_end, self._db)
            app = await self._db.get(AppProfile, cid)
            name = app.app_name if app else str(cid)
            competitors_data.append({"app_id": str(cid), "app_name": name, **cm})
        all_metrics["competitors"] = competitors_data

        # Build comparison summary
        summary = _build_comparison_summary(
            target_metrics,
            competitors_data,
            req.target_app_id,
        )

        benchmark = AppBenchmark(
            target_app_id=req.target_app_id,
            competitor_app_ids=[str(c) for c in req.competitor_app_ids],
            period_start=req.period_start,
            period_end=req.period_end,
            metrics=all_metrics,
            comparison_summary=summary,
        )
        self._db.add(benchmark)
        await self._db.commit()
        await self._db.refresh(benchmark)
        return benchmark


def _build_comparison_summary(
    target: dict,
    competitors: list[dict],
    target_app_id,
) -> str:
    if not competitors:
        return "경쟁사 데이터가 없어 단독 분석만 제공됩니다."

    avg_comp_rating = sum(c["average_rating"] for c in competitors) / len(competitors)
    avg_comp_neg = sum(c["negative_ratio"] for c in competitors) / len(competitors)

    lines: list[str] = []
    t_rating = target["average_rating"]
    t_neg = target["negative_ratio"]

    if t_rating < avg_comp_rating:
        diff = round(avg_comp_rating - t_rating, 2)
        lines.append(f"평균 평점이 경쟁사 대비 {diff}점 낮습니다.")
    else:
        diff = round(t_rating - avg_comp_rating, 2)
        lines.append(f"평균 평점이 경쟁사 대비 {diff}점 높습니다.")

    if t_neg > avg_comp_neg:
        pct = round((t_neg - avg_comp_neg) * 100, 1)
        lines.append(f"부정 리뷰 비율이 경쟁사 평균보다 {pct}%p 높습니다.")
    else:
        pct = round((avg_comp_neg - t_neg) * 100, 1)
        lines.append(f"부정 리뷰 비율이 경쟁사 평균보다 {pct}%p 낮습니다.")

    if target.get("critical_issue_count", 0) > 0:
        lines.append(f"Critical 이슈 클러스터가 {target['critical_issue_count']}개 존재합니다. 즉각적인 대응이 필요합니다.")

    return " ".join(lines)

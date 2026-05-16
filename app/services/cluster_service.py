"""Rule-based review clustering for Phase 2 MVP.

Groups reviews by (category, rating band) without requiring embeddings.
"""

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.classification import ClassificationResult
from app.models.review import Review
from app.models.review_cluster import ClusterSeverity, IssueType, ReviewCluster

# Map review category → cluster issue_type
_CATEGORY_TO_ISSUE: dict[str, IssueType] = {
    "login_account": IssueType.AUTHENTICATION,
    "login_authentication": IssueType.AUTHENTICATION,
    "certificate": IssueType.AUTHENTICATION,
    "bug": IssueType.BUG,
    "update_regression": IssueType.BUG,
    "app_crash": IssueType.PERFORMANCE,
    "app_speed": IssueType.PERFORMANCE,
    "performance": IssueType.PERFORMANCE,
    "payment": IssueType.OPERATION,
    "refund": IssueType.OPERATION,
    "transfer_remittance": IssueType.OPERATION,
    "security_concern": IssueType.SECURITY,
    "ux_ui": IssueType.UX,
    "ui_complexity": IssueType.UX,
    "senior_accessibility": IssueType.UX,
    "customer_center": IssueType.CUSTOMER_SUPPORT,
    "customer_support": IssueType.CUSTOMER_SUPPORT,
    "policy_complaint": IssueType.POLICY,
    "policy_inquiry": IssueType.POLICY,
    "benefit_point": IssueType.PRICING,
    "pricing": IssueType.PRICING,
    "notification": IssueType.OPERATION,
}

_CATEGORY_LABELS: dict[str, str] = {
    "login_account": "로그인/계정 문제",
    "login_authentication": "로그인/인증 문제",
    "certificate": "공동인증서 문제",
    "bug": "버그/오류",
    "update_regression": "업데이트 후 오류",
    "app_crash": "앱 튕김/충돌",
    "app_speed": "앱 속도/성능",
    "performance": "성능 문제",
    "payment": "결제 문제",
    "refund": "환불 문제",
    "transfer_remittance": "이체/송금 문제",
    "security_concern": "보안 우려",
    "ux_ui": "UX/UI 불편",
    "ui_complexity": "메뉴 복잡성",
    "senior_accessibility": "고령자 접근성",
    "customer_center": "고객센터 불만",
    "customer_support": "고객지원 문제",
    "policy_complaint": "정책 불만",
    "policy_inquiry": "정책 문의",
    "benefit_point": "혜택/포인트 불만",
    "pricing": "요금/가격 문제",
    "notification": "알림 과다",
    "other": "기타 불만",
}


def _severity(neg_ratio: float, review_count: int, avg_rating: float | None) -> ClusterSeverity:
    if neg_ratio >= 0.8 or (avg_rating and avg_rating <= 1.5 and review_count >= 10):
        return ClusterSeverity.CRITICAL
    if neg_ratio >= 0.6 or (avg_rating and avg_rating <= 2.0):
        return ClusterSeverity.HIGH
    if neg_ratio >= 0.4:
        return ClusterSeverity.MEDIUM
    return ClusterSeverity.LOW


class ClusterService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def cluster(self, app_id: uuid.UUID) -> list[ReviewCluster]:
        # Load all classified reviews for this app
        rows = await self._db.execute(
            select(Review, ClassificationResult)
            .outerjoin(ClassificationResult, ClassificationResult.review_id == Review.id)
            .where(Review.app_id == app_id)
        )
        pairs = rows.all()

        # Group by primary category
        groups: dict[str, list[tuple[Review, ClassificationResult | None]]] = defaultdict(list)
        for review, cls in pairs:
            cats = cls.categories if cls and cls.categories else ["other"]
            primary = cats[0] if cats else "other"
            groups[primary].append((review, cls))

        # Delete existing clusters for this app
        existing = await self._db.execute(
            select(ReviewCluster).where(ReviewCluster.app_id == app_id)
        )
        for c in existing.scalars().all():
            await self._db.delete(c)

        new_clusters: list[ReviewCluster] = []
        for category, items in groups.items():
            if len(items) < 2:
                continue

            ratings = [r.rating for r, _ in items if r.rating is not None]
            avg_rating = sum(ratings) / len(ratings) if ratings else None
            neg_count = sum(1 for r, _ in items if r.rating and r.rating <= 2)
            neg_ratio = neg_count / len(items)

            # Pick up to 5 representative reviews (lowest rated)
            sorted_items = sorted(items, key=lambda x: (x[0].rating or 5, -x[0].id))
            rep_ids = [r.id for r, _ in sorted_items[:5]]

            label = _CATEGORY_LABELS.get(category, category)
            issue_type = _CATEGORY_TO_ISSUE.get(category, IssueType.UNKNOWN)
            severity = _severity(neg_ratio, len(items), avg_rating)

            # Build summary
            top_texts = [r.normalized_text[:100] for r, _ in sorted_items[:3]]
            summary = f"'{label}' 관련 리뷰 {len(items)}건. 대표 리뷰: {' / '.join(top_texts)}"

            cluster = ReviewCluster(
                app_id=app_id,
                title=label,
                summary=summary,
                issue_type=issue_type,
                review_count=len(items),
                negative_ratio=round(neg_ratio, 3),
                average_rating=round(avg_rating, 2) if avg_rating else None,
                severity=severity,
                representative_review_ids=[str(r) for r in rep_ids],
            )
            self._db.add(cluster)
            new_clusters.append(cluster)

        await self._db.commit()
        for c in new_clusters:
            await self._db.refresh(c)
        return new_clusters

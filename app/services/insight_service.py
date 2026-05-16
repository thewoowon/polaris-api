"""Generate actionable insights from review clusters."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_profile import AppProfile
from app.models.insight import (
    BusinessImpact,
    Insight,
    InsightSeverity,
    InsightType,
)
from app.models.review import Review
from app.models.review_cluster import ClusterSeverity, IssueType, ReviewCluster

_ISSUE_TO_INSIGHT: dict[IssueType, InsightType] = {
    IssueType.AUTHENTICATION: InsightType.TECHNICAL_ISSUE,
    IssueType.BUG: InsightType.TECHNICAL_ISSUE,
    IssueType.PERFORMANCE: InsightType.TECHNICAL_ISSUE,
    IssueType.UX: InsightType.UX_PROBLEM,
    IssueType.SECURITY: InsightType.RISK,
    IssueType.OPERATION: InsightType.OPERATION_ISSUE,
    IssueType.CUSTOMER_SUPPORT: InsightType.CUSTOMER_SUPPORT_ISSUE,
    IssueType.POLICY: InsightType.RISK,
    IssueType.PRICING: InsightType.COMPETITIVE_GAP,
    IssueType.UNKNOWN: InsightType.RISK,
}

_ISSUE_TO_IMPACT: dict[IssueType, BusinessImpact] = {
    IssueType.AUTHENTICATION: BusinessImpact.RETENTION,
    IssueType.BUG: BusinessImpact.RETENTION,
    IssueType.PERFORMANCE: BusinessImpact.RETENTION,
    IssueType.UX: BusinessImpact.CONVERSION,
    IssueType.SECURITY: BusinessImpact.TRUST,
    IssueType.OPERATION: BusinessImpact.COST,
    IssueType.CUSTOMER_SUPPORT: BusinessImpact.TRUST,
    IssueType.POLICY: BusinessImpact.COMPLIANCE,
    IssueType.PRICING: BusinessImpact.CONVERSION,
    IssueType.UNKNOWN: BusinessImpact.UNKNOWN,
}

_SEVERITY_MAP: dict[ClusterSeverity, InsightSeverity] = {
    ClusterSeverity.CRITICAL: InsightSeverity.CRITICAL,
    ClusterSeverity.HIGH: InsightSeverity.HIGH,
    ClusterSeverity.MEDIUM: InsightSeverity.MEDIUM,
    ClusterSeverity.LOW: InsightSeverity.LOW,
}

_ACTION_TEMPLATES: dict[IssueType, str] = {
    IssueType.AUTHENTICATION: (
        "인증 플로우 안정성 점검이 필요합니다. "
        "공동인증서 이동, 지문인식, 간편비밀번호 각각의 실패 케이스를 로그로 수집하고 "
        "빠른 패치를 통해 인증 실패율을 낮춰야 합니다."
    ),
    IssueType.BUG: (
        "최근 업데이트 이후 발생한 버그를 우선 수정합니다. "
        "크래시 리포트를 분석하여 재현 경로를 확인하고, "
        "핫픽스 릴리즈를 검토하세요."
    ),
    IssueType.PERFORMANCE: (
        "앱 응답 속도 개선이 필요합니다. "
        "주요 화면(잔액조회, 이체)의 로딩 시간을 측정하고, "
        "캐싱 전략 및 API 최적화를 검토하세요."
    ),
    IssueType.UX: (
        "UX/UI 개편을 검토합니다. "
        "주요 기능(이체, 혜택, 조회)의 접근 경로를 단순화하고, "
        "경쟁사 대비 사용성 테스트를 진행하세요."
    ),
    IssueType.SECURITY: (
        "보안 관련 사용자 우려를 모니터링합니다. "
        "보안 공지를 명확히 하고, 의심스러운 케이스는 CS와 연계하세요."
    ),
    IssueType.OPERATION: (
        "운영 프로세스 개선이 필요합니다. "
        "해당 기능의 오류율 및 처리 지연을 모니터링하고, "
        "CS 응대 가이드를 업데이트하세요."
    ),
    IssueType.CUSTOMER_SUPPORT: (
        "고객 지원 채널 개선이 필요합니다. "
        "인앱 문의 접근성을 높이고, 주요 VOC 유형에 대한 응대 스크립트를 정비하세요."
    ),
    IssueType.POLICY: (
        "정책 안내 방식을 개선합니다. "
        "변경 사항은 푸시 알림과 인앱 공지로 사전 안내하고, "
        "FAQ를 업데이트하세요."
    ),
    IssueType.PRICING: (
        "혜택 및 수수료 정책의 가시성을 높입니다. "
        "경쟁사 혜택과의 비교를 통해 개선 방향을 검토하세요."
    ),
    IssueType.UNKNOWN: (
        "해당 불만 유형을 추가로 분류하여 담당 부서에 전달하세요."
    ),
}


def _build_summary(cluster: ReviewCluster, rep_reviews: list[Review]) -> str:
    rep_texts = " / ".join(f'"{r.normalized_text[:80]}"' for r in rep_reviews[:2])
    return (
        f"'{cluster.title}' 관련 불만이 {cluster.review_count}건 반복적으로 나타납니다 "
        f"(부정 비율 {cluster.negative_ratio * 100:.0f}%). "
        f"대표 리뷰: {rep_texts}. "
        f"심각도는 {cluster.severity.value}로 평가됩니다."
    )


class InsightService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def generate(self, app: AppProfile) -> list[Insight]:
        # Load clusters
        cluster_rows = await self._db.execute(
            select(ReviewCluster)
            .where(ReviewCluster.app_id == app.id)
            .order_by(ReviewCluster.review_count.desc())
        )
        clusters = cluster_rows.scalars().all()

        # Delete existing insights
        existing = await self._db.execute(
            select(Insight).where(Insight.app_id == app.id)
        )
        for ins in existing.scalars().all():
            await self._db.delete(ins)

        new_insights: list[Insight] = []
        for cluster in clusters:
            # Get representative reviews
            rep_review_ids = cluster.representative_review_ids or []
            rep_reviews: list[Review] = []
            for rid in rep_review_ids[:3]:
                try:
                    r = await self._db.get(Review, int(rid))
                    if r:
                        rep_reviews.append(r)
                except (ValueError, TypeError):
                    pass

            insight_type = _ISSUE_TO_INSIGHT.get(cluster.issue_type, InsightType.RISK)
            business_impact = _ISSUE_TO_IMPACT.get(cluster.issue_type, BusinessImpact.UNKNOWN)
            severity = _SEVERITY_MAP.get(cluster.severity, InsightSeverity.MEDIUM)
            action = _ACTION_TEMPLATES.get(cluster.issue_type, _ACTION_TEMPLATES[IssueType.UNKNOWN])
            summary = _build_summary(cluster, rep_reviews)

            insight = Insight(
                app_id=app.id,
                company_id=app.company_id,
                insight_type=insight_type,
                title=f"{cluster.title} 개선 필요",
                summary=summary,
                evidence_review_ids=[str(r.id) for r in rep_reviews],
                severity=severity,
                business_impact=business_impact,
                recommended_action=action,
            )
            self._db.add(insight)
            new_insights.append(insight)

        await self._db.commit()
        for ins in new_insights:
            await self._db.refresh(ins)
        return new_insights

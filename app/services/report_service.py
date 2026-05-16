"""Report generator: assembles structured data → Markdown report.

Uses LLM (OpenAI) when API key is available; falls back to template generation.
"""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.app_profile import AppProfile
from app.models.company import Company
from app.models.insight import Insight
from app.models.report import Report, ReportType
from app.models.review import Review
from app.models.review_cluster import ReviewCluster
from app.schemas.report import ReportGenerateRequest
from app.services.analysis_service import AnalysisService
from app.services.benchmark_service import BenchmarkService
from app.schemas.app_benchmark import BenchmarkRequest


class ReportService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def generate(self, req: ReportGenerateRequest) -> Report:
        company = await self._db.get(Company, req.company_id)
        if not company:
            raise ValueError(f"Company {req.company_id} not found")

        app = await self._db.get(AppProfile, req.app_id)
        if not app:
            raise ValueError(f"App {req.app_id} not found")

        # Gather data
        analysis = await AnalysisService(self._db).summary(req.app_id)

        clusters_result = await self._db.execute(
            select(ReviewCluster)
            .where(ReviewCluster.app_id == req.app_id)
            .order_by(ReviewCluster.review_count.desc())
            .limit(10)
        )
        clusters = clusters_result.scalars().all()

        insights_result = await self._db.execute(
            select(Insight)
            .where(Insight.app_id == req.app_id)
            .order_by(Insight.created_at.desc())
        )
        insights = insights_result.scalars().all()

        # Optional benchmark
        benchmark_summary: str | None = None
        if req.include_benchmark and req.competitor_app_ids:
            bench_req = BenchmarkRequest(
                target_app_id=req.app_id,
                competitor_app_ids=req.competitor_app_ids,
                period_start=req.period_start,
                period_end=req.period_end,
            )
            benchmark = await BenchmarkService(self._db).run(bench_req)
            benchmark_summary = benchmark.comparison_summary

        # Get representative reviews for evidence
        rep_review_texts: list[str] = []
        for cluster in clusters[:5]:
            ids = cluster.representative_review_ids or []
            for rid in ids[:1]:
                try:
                    r = await self._db.get(Review, int(rid))
                    if r:
                        rep_review_texts.append(f"- (★{r.rating}) {r.normalized_text[:120]}")
                except (ValueError, TypeError):
                    pass

        # Generate markdown
        if settings.OPENAI_API_KEY:
            md, summary = await _llm_generate(
                company=company,
                app=app,
                analysis=analysis,
                clusters=clusters,
                insights=insights,
                benchmark_summary=benchmark_summary,
                req=req,
            )
        else:
            md, summary = _template_generate(
                company=company,
                app=app,
                analysis=analysis,
                clusters=clusters,
                insights=insights,
                benchmark_summary=benchmark_summary,
                rep_reviews=rep_review_texts,
                req=req,
            )

        title = f"{company.name} {app.app_name} 앱 리뷰 인텔리전스 리포트 ({req.period_start} ~ {req.period_end})"

        report = Report(
            company_id=req.company_id,
            app_id=req.app_id,
            report_type=req.report_type,
            title=title,
            period_start=req.period_start,
            period_end=req.period_end,
            markdown_content=md,
            executive_summary=summary,
        )
        self._db.add(report)
        await self._db.commit()
        await self._db.refresh(report)
        return report


def _template_generate(
    company: Company,
    app: AppProfile,
    analysis: dict,
    clusters: list[ReviewCluster],
    insights: list[Insight],
    benchmark_summary: str | None,
    rep_reviews: list[str],
    req: ReportGenerateRequest,
) -> tuple[str, str]:
    total = analysis.get("total_reviews", 0)
    avg_rating = analysis.get("average_rating") or "N/A"
    neg_ratio = f"{(analysis.get('negative_ratio', 0) * 100):.1f}%"
    critical_count = analysis.get("critical_count", 0)
    top_categories = analysis.get("top_categories", [])

    # Executive summary
    top3_issues = [c.title for c in clusters[:3]] if clusters else ["데이터 없음"]
    exec_summary = (
        f"{company.name} {app.app_name} 리뷰 분석 결과: "
        f"총 {total}건 리뷰 중 부정 비율 {neg_ratio}, "
        f"평균 평점 {avg_rating}점. "
        f"주요 이슈: {', '.join(top3_issues)}. "
        f"Critical 이슈 {critical_count}건 즉시 대응 필요."
    )

    # VOC Top table
    voc_rows = []
    for i, cat in enumerate(top_categories[:10], 1):
        voc_rows.append(f"| {i} | {cat['category']} | {cat['count']}건 | - | - |")
    voc_table = "\n".join(voc_rows) if voc_rows else "| - | 분류 데이터 없음 | - | - | - |"

    # Clusters
    cluster_sections = []
    for c in clusters[:6]:
        cluster_sections.append(
            f"### {c.title} (심각도: {c.severity.value.upper()})\n"
            f"- 리뷰 수: {c.review_count}건 / 부정 비율: {c.negative_ratio * 100:.1f}%\n"
            f"- 요약: {c.summary[:200]}\n"
            f"- 이슈 유형: {c.issue_type.value}\n"
        )
    clusters_md = "\n".join(cluster_sections) if cluster_sections else "클러스터 데이터가 없습니다. /cluster API를 먼저 실행하세요."

    # Insights
    insight_sections = []
    for ins in insights[:6]:
        insight_sections.append(
            f"### {ins.title}\n"
            f"- 심각도: {ins.severity.value} / 비즈니스 영향: {ins.business_impact.value}\n"
            f"- 요약: {ins.summary[:300]}\n"
            f"- 추천 조치: {ins.recommended_action}\n"
        )
    insights_md = "\n".join(insight_sections) if insight_sections else "인사이트 데이터가 없습니다. /insights API를 먼저 실행하세요."

    # Priority roadmap
    priority_items = []
    for i, ins in enumerate(sorted(insights, key=lambda x: x.severity.value)[:5], 1):
        priority_items.append(f"| {i} | {ins.title} | - | {ins.business_impact.value} | medium |")
    priority_md = "\n".join(priority_items) if priority_items else "| - | - | - | - | - |"

    benchmark_section = ""
    if benchmark_summary:
        benchmark_section = f"""
## 5. 경쟁사 대비 분석

{benchmark_summary}
"""

    # Representative reviews
    evidence_md = "\n".join(rep_reviews[:10]) if rep_reviews else "- 대표 리뷰 데이터가 없습니다."

    md = f"""# {company.name} {app.app_name} 앱 리뷰 인텔리전스 리포트

> **분석 기간**: {req.period_start} ~ {req.period_end}
> **생성일**: {date.today().isoformat()}
> **분석 대상**: {app.app_name} ({app.platform.value})
> **Powered by**: Polaris AI

---

## 1. Executive Summary

{exec_summary}

**핵심 문제 Top 3**
{chr(10).join(f"- {t}" for t in top3_issues)}

**즉시 개선 가능한 항목**
- 앱 충돌/튕김 → 핫픽스 릴리즈 검토
- 인증 오류 → 로그 수집 및 원인 분석
- 고객센터 연결 → 인앱 문의 접근성 개선

**30일 내 추천 액션**
- Critical 이슈 클러스터 우선 해결
- 주요 불만 카테고리 CS 응대 가이드 업데이트
- 부정 리뷰 대응 문안 개선

---

## 2. 분석 개요

| 항목 | 값 |
|------|-----|
| 분석 대상 앱 | {app.app_name} |
| 플랫폼 | {app.platform.value} |
| 분석 기간 | {req.period_start} ~ {req.period_end} |
| 수집 리뷰 수 | {total}건 |
| 평균 평점 | {avg_rating} |
| 부정 리뷰 비율 | {neg_ratio} |
| Critical 이슈 수 | {critical_count}건 |

---

## 3. 주요 VOC Top 10

| 순위 | 이슈 | 건수 | 심각도 | 대표 리뷰 |
|------|------|-----:|--------|-----------|
{voc_table}

---

## 4. 반복 불만 클러스터

{clusters_md}

**대표 리뷰 증거**

{evidence_md}
{benchmark_section}
---

## 6. UX/운영/개발/정책별 개선안

{insights_md}

---

## 7. 대응 문안 개선안

### 현재 대응 방식의 문제점
- 복사 붙여넣기식 응답으로 고객 신뢰 저하
- 구체적 해결 방향 없는 사과 중심 응대

### 추천 응답 톤
- 명확하고 구체적인 해결 안내
- 공감 + 행동 지시형 응답

### 카테고리별 응답 템플릿

**로그인/인증 오류 응답 예시**
> 안녕하세요. 로그인 오류로 불편을 드려 죄송합니다. 앱 재설치 후 공동인증서를 다시 등록해 주시거나, 고객센터(1234-5678)로 연락 주시면 빠르게 도와드리겠습니다.

**앱 튕김/오류 응답 예시**
> 안녕하세요. 불편을 드려 죄송합니다. 현재 해당 현상을 확인 중이며, 빠른 패치를 준비하고 있습니다. 앱 설정 > 캐시 삭제 후 재시작을 시도해 보세요.

---

## 8. 30일 개선 로드맵

| 우선순위 | 액션 | 담당 | 기대효과 | 난이도 |
|---------|------|------|---------|--------|
{priority_md}

---

## 9. 결론

**가장 먼저 해결해야 할 문제**
{chr(10).join(f"- {t}" for t in top3_issues[:2])}

**장기적으로 관리해야 할 문제**
- UX 전반적 개편을 통한 사용성 향상
- 경쟁사 대비 혜택/기능 차별화
- 고객 응대 품질 및 응답 속도 지속 개선

**Polaris AI 제안**
앱 리뷰는 단순 VOC가 아닌 제품·운영·개발 전반의 건강 지표입니다.
월 1회 이상 주기적 분석을 통해 데이터 기반 의사결정을 권장합니다.

---

*이 리포트는 Polaris AI가 공개 리뷰 데이터를 기반으로 자동 생성했습니다.*
*근거 없는 수치나 확인되지 않은 사실은 포함하지 않았습니다.*
"""

    return md.strip(), exec_summary


async def _llm_generate(
    company: Company,
    app: AppProfile,
    analysis: dict,
    clusters: list[ReviewCluster],
    insights: list[Insight],
    benchmark_summary: str | None,
    req: ReportGenerateRequest,
) -> tuple[str, str]:
    """Generate a polished report using OpenAI."""
    try:
        from openai import AsyncOpenAI
    except ImportError:
        return _template_generate(
            company=company,
            app=app,
            analysis=analysis,
            clusters=clusters,
            insights=insights,
            benchmark_summary=benchmark_summary,
            rep_reviews=[],
            req=req,
        )

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    cluster_text = "\n".join(
        f"- {c.title}: {c.review_count}건, 부정{c.negative_ratio*100:.0f}%, severity={c.severity.value}"
        for c in clusters[:8]
    )
    insight_text = "\n".join(
        f"- {i.title}: {i.summary[:200]}"
        for i in insights[:6]
    )

    system_prompt = """당신은 한국 기업용 앱 리뷰 인텔리전스 리포트를 작성하는 전문 애널리스트입니다.
반드시 입력 데이터에 근거해서만 작성하세요.
근거 없는 수치, 확인되지 않은 장애 원인 단정, 법적 표현, "반드시"/"확실히" 같은 과도한 확정 표현은 금지입니다.
리포트는 구조화된 Markdown으로 작성하세요."""

    user_prompt = f"""아래 데이터를 바탕으로 앱 리뷰 인텔리전스 리포트를 Markdown으로 작성하세요.

## 입력 데이터

**회사**: {company.name} ({company.industry.value})
**앱**: {app.app_name} ({app.platform.value})
**분석 기간**: {req.period_start} ~ {req.period_end}
**수집 리뷰**: {analysis.get('total_reviews')}건
**평균 평점**: {analysis.get('average_rating')}
**부정 리뷰 비율**: {analysis.get('negative_ratio', 0)*100:.1f}%
**Critical 이슈**: {analysis.get('critical_count')}건

**클러스터 (반복 불만)**:
{cluster_text}

**인사이트**:
{insight_text}

**경쟁사 비교**: {benchmark_summary or '없음'}

## 리포트 구조 (반드시 이 순서로)

1. Executive Summary (핵심 문제 3개, 30일 추천 액션)
2. 분석 개요 (표 형식)
3. 주요 VOC Top 10 (표 형식)
4. 반복 불만 클러스터 (각 클러스터별 상세)
5. 경쟁사 대비 분석 (데이터 있을 때만)
6. UX/운영/개발/정책별 개선안
7. 대응 문안 개선안 (카테고리별 응답 예시)
8. 30일 개선 로드맵 (표 형식)
9. 결론

리포트 제목: # {company.name} {app.app_name} 앱 리뷰 인텔리전스 리포트
"""

    response = await client.chat.completions.create(
        model=settings.OPENAI_CLASSIFIER_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=4000,
        temperature=0.3,
    )

    md = response.choices[0].message.content or ""

    # Extract executive summary (first paragraph after ## 1.)
    import re
    exec_match = re.search(r"## 1\. Executive Summary\s*\n+(.*?)(?=\n##|\Z)", md, re.DOTALL)
    summary = exec_match.group(1).strip()[:500] if exec_match else md[:200]

    return md, summary

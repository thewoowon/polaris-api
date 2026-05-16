import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.app_profile import AppProfile
from app.models.company import Company
from app.models.review import Review
from app.models.review_cluster import ReviewCluster
from app.models.insight import Insight
from app.schemas.app_profile import AppProfileCreate, AppProfileResponse, AppProfileUpdate
from app.schemas.common import Page
from app.schemas.review_cluster import ReviewClusterResponse
from app.schemas.insight import InsightResponse
from app.services.cluster_service import ClusterService
from app.services.insight_service import InsightService
from app.services.mock_ingestion import MockIngestionService
from app.services.analysis_service import AnalysisService

router = APIRouter()


async def _get_or_404(app_id: uuid.UUID, db: AsyncSession) -> AppProfile:
    row = await db.get(AppProfile, app_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")
    return row


async def _enrich(app: AppProfile, db: AsyncSession) -> AppProfileResponse:
    resp = AppProfileResponse.model_validate(app)

    # company_name
    company = await db.get(Company, app.company_id)
    resp.company_name = company.name if company else None

    # stats
    result = await db.execute(
        select(
            func.count(Review.id),
            func.avg(Review.rating),
        ).where(Review.app_id == app.id)
    )
    row = result.one()
    resp.review_count = row[0] or 0
    resp.average_rating = round(float(row[1]), 2) if row[1] else None

    if resp.review_count > 0:
        neg_result = await db.execute(
            select(func.count(Review.id)).where(
                Review.app_id == app.id,
                Review.rating <= 2,
            )
        )
        neg_count = neg_result.scalar_one()
        resp.negative_ratio = round(neg_count / resp.review_count, 3)

    return resp


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=Page[AppProfileResponse])
async def list_apps(
    company_id: uuid.UUID | None = Query(None),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> Page[AppProfileResponse]:
    q = select(AppProfile)
    if company_id:
        q = q.where(AppProfile.company_id == company_id)

    total_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = total_result.scalar_one()

    rows = await db.execute(q.order_by(AppProfile.created_at.desc()).limit(limit).offset(offset))
    apps = rows.scalars().all()

    items = [await _enrich(a, db) for a in apps]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=AppProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_app(
    body: AppProfileCreate,
    db: AsyncSession = Depends(get_db),
) -> AppProfileResponse:
    if not await db.get(Company, body.company_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    app = AppProfile(**body.model_dump())
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return await _enrich(app, db)


@router.get("/{app_id}", response_model=AppProfileResponse)
async def get_app(app_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> AppProfileResponse:
    app = await _get_or_404(app_id, db)
    return await _enrich(app, db)


@router.patch("/{app_id}", response_model=AppProfileResponse)
async def update_app(
    app_id: uuid.UUID,
    body: AppProfileUpdate,
    db: AsyncSession = Depends(get_db),
) -> AppProfileResponse:
    app = await _get_or_404(app_id, db)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(app, field, value)
    await db.commit()
    await db.refresh(app)
    return await _enrich(app, db)


@router.delete("/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_app(app_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    app = await _get_or_404(app_id, db)
    await db.delete(app)
    await db.commit()


# ── Mock Ingestion ────────────────────────────────────────────────────────────

@router.post("/{app_id}/ingest/mock")
async def mock_ingest(
    app_id: uuid.UUID,
    count: int = Query(100, ge=10, le=500),
    db: AsyncSession = Depends(get_db),
) -> dict:
    app = await _get_or_404(app_id, db)
    svc = MockIngestionService(db)
    created = await svc.generate(app, count)
    return {"created": created, "app_id": str(app_id)}


# ── Analysis ──────────────────────────────────────────────────────────────────

@router.get("/{app_id}/summary")
async def app_summary(app_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    await _get_or_404(app_id, db)
    return await AnalysisService(db).summary(app_id)


@router.get("/{app_id}/trends")
async def app_trends(
    app_id: uuid.UUID,
    days: int = Query(30, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _get_or_404(app_id, db)
    return await AnalysisService(db).trends(app_id, days)


# ── Clustering ────────────────────────────────────────────────────────────────

@router.post("/{app_id}/cluster", response_model=list[ReviewClusterResponse])
async def run_clustering(app_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[ReviewClusterResponse]:
    await _get_or_404(app_id, db)
    clusters = await ClusterService(db).cluster(app_id)
    return [ReviewClusterResponse.model_validate(c) for c in clusters]


@router.get("/{app_id}/clusters", response_model=list[ReviewClusterResponse])
async def list_clusters(app_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[ReviewClusterResponse]:
    await _get_or_404(app_id, db)
    rows = await db.execute(
        select(ReviewCluster).where(ReviewCluster.app_id == app_id).order_by(ReviewCluster.review_count.desc())
    )
    return [ReviewClusterResponse.model_validate(c) for c in rows.scalars().all()]


# ── Insights ──────────────────────────────────────────────────────────────────

@router.post("/{app_id}/insights", response_model=list[InsightResponse])
async def generate_insights(app_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[InsightResponse]:
    app = await _get_or_404(app_id, db)
    insights = await InsightService(db).generate(app)
    return [InsightResponse.model_validate(i) for i in insights]


@router.get("/{app_id}/insights", response_model=list[InsightResponse])
async def list_insights(app_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[InsightResponse]:
    await _get_or_404(app_id, db)
    rows = await db.execute(
        select(Insight).where(Insight.app_id == app_id).order_by(Insight.created_at.desc())
    )
    return [InsightResponse.model_validate(i) for i in rows.scalars().all()]

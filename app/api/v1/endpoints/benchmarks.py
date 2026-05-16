import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.app_benchmark import AppBenchmark
from app.models.app_profile import AppProfile
from app.schemas.app_benchmark import AppBenchmarkResponse, BenchmarkRequest
from app.services.benchmark_service import BenchmarkService

router = APIRouter()


@router.post("", response_model=AppBenchmarkResponse, status_code=status.HTTP_201_CREATED)
async def create_benchmark(
    body: BenchmarkRequest,
    db: AsyncSession = Depends(get_db),
) -> AppBenchmarkResponse:
    if not await db.get(AppProfile, body.target_app_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target app not found")

    svc = BenchmarkService(db)
    benchmark = await svc.run(body)
    return AppBenchmarkResponse.model_validate(benchmark)


@router.get("/{benchmark_id}", response_model=AppBenchmarkResponse)
async def get_benchmark(
    benchmark_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AppBenchmarkResponse:
    row = await db.get(AppBenchmark, benchmark_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benchmark not found")
    return AppBenchmarkResponse.model_validate(row)


@router.get("", response_model=list[AppBenchmarkResponse])
async def list_benchmarks(
    target_app_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[AppBenchmarkResponse]:
    q = select(AppBenchmark).order_by(AppBenchmark.created_at.desc())
    if target_app_id:
        q = q.where(AppBenchmark.target_app_id == target_app_id)
    rows = await db.execute(q)
    return [AppBenchmarkResponse.model_validate(b) for b in rows.scalars().all()]

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.company import Company
from app.models.app_profile import AppProfile
from app.models.report import Report
from app.schemas.report import ReportGenerateRequest, ReportResponse, ReportStatusUpdate
from app.schemas.common import Page
from app.services.report_service import ReportService

router = APIRouter()


async def _enrich(report: Report, db: AsyncSession) -> ReportResponse:
    resp = ReportResponse.model_validate(report)
    company = await db.get(Company, report.company_id)
    resp.company_name = company.name if company else None
    if report.app_id:
        app = await db.get(AppProfile, report.app_id)
        resp.app_name = app.app_name if app else None
    return resp


@router.post("/generate", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def generate_report(
    body: ReportGenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> ReportResponse:
    try:
        svc = ReportService(db)
        report = await svc.generate(body)
        return await _enrich(report, db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("", response_model=Page[ReportResponse])
async def list_reports(
    company_id: uuid.UUID | None = Query(None),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> Page[ReportResponse]:
    from sqlalchemy import func
    q = select(Report)
    if company_id:
        q = q.where(Report.company_id == company_id)

    total_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = total_result.scalar_one()

    rows = await db.execute(q.order_by(Report.created_at.desc()).limit(limit).offset(offset))
    reports = rows.scalars().all()

    items = [await _enrich(r, db) for r in reports]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(report_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ReportResponse:
    report = await db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return await _enrich(report, db)


@router.patch("/{report_id}", response_model=ReportResponse)
async def update_report_status(
    report_id: uuid.UUID,
    body: ReportStatusUpdate,
    db: AsyncSession = Depends(get_db),
) -> ReportResponse:
    report = await db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    report.status = body.status
    await db.commit()
    await db.refresh(report)
    return await _enrich(report, db)


@router.post("/{report_id}/export-markdown")
async def export_markdown(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    report = await db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return {"markdown": report.markdown_content, "title": report.title}

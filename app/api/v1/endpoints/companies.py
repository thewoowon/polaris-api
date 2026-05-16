import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.app_profile import AppProfile
from app.models.company import Company
from app.schemas.common import Page
from app.schemas.company import CompanyCreate, CompanyResponse, CompanyUpdate

router = APIRouter()


async def _get_or_404(company_id: uuid.UUID, db: AsyncSession) -> Company:
    row = await db.get(Company, company_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return row


@router.get("", response_model=Page[CompanyResponse])
async def list_companies(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> Page[CompanyResponse]:
    total_result = await db.execute(select(func.count()).select_from(Company))
    total = total_result.scalar_one()

    rows = await db.execute(select(Company).order_by(Company.created_at.desc()).limit(limit).offset(offset))
    companies = rows.scalars().all()

    items = []
    for c in companies:
        count_result = await db.execute(
            select(func.count()).select_from(AppProfile).where(AppProfile.company_id == c.id)
        )
        app_count = count_result.scalar_one()
        resp = CompanyResponse.model_validate(c)
        resp.app_count = app_count
        items.append(resp)

    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
async def create_company(
    body: CompanyCreate,
    db: AsyncSession = Depends(get_db),
) -> CompanyResponse:
    company = Company(**body.model_dump())
    db.add(company)
    await db.commit()
    await db.refresh(company)
    resp = CompanyResponse.model_validate(company)
    resp.app_count = 0
    return resp


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> CompanyResponse:
    company = await _get_or_404(company_id, db)
    count_result = await db.execute(
        select(func.count()).select_from(AppProfile).where(AppProfile.company_id == company_id)
    )
    resp = CompanyResponse.model_validate(company)
    resp.app_count = count_result.scalar_one()
    return resp


@router.patch("/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: uuid.UUID,
    body: CompanyUpdate,
    db: AsyncSession = Depends(get_db),
) -> CompanyResponse:
    company = await _get_or_404(company_id, db)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(company, field, value)
    await db.commit()
    await db.refresh(company)
    count_result = await db.execute(
        select(func.count()).select_from(AppProfile).where(AppProfile.company_id == company_id)
    )
    resp = CompanyResponse.model_validate(company)
    resp.app_count = count_result.scalar_one()
    return resp


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    company = await _get_or_404(company_id, db)
    await db.delete(company)
    await db.commit()

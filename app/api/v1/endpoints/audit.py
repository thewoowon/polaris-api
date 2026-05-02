from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.audit import AuditLog
from app.schemas.audit import AuditLogResponse
from app.schemas.common import Page

router = APIRouter()


@router.get("", response_model=Page[AuditLogResponse])
async def list_audit(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    entity_type: str | None = Query(None),
    entity_id: int | None = Query(None),
    action: str | None = Query(None),
    actor: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> Page[AuditLogResponse]:
    base = select(AuditLog)
    count_base = select(func.count()).select_from(AuditLog)

    if entity_type:
        base = base.where(AuditLog.entity_type == entity_type)
        count_base = count_base.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        base = base.where(AuditLog.entity_id == entity_id)
        count_base = count_base.where(AuditLog.entity_id == entity_id)
    if action:
        base = base.where(AuditLog.action == action)
        count_base = count_base.where(AuditLog.action == action)
    if actor:
        base = base.where(AuditLog.actor == actor)
        count_base = count_base.where(AuditLog.actor == actor)

    total = (await db.execute(count_base)).scalar_one() or 0
    rows = (
        await db.execute(
            base.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()

    return Page[AuditLogResponse](
        items=[AuditLogResponse.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )

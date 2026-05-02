from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.kb import KbDocument
from app.schemas.common import Page
from app.schemas.kb import (
    KbDocumentCreate,
    KbDocumentResponse,
    KbDocumentUpdate,
    KbSearchHit,
    KbSearchRequest,
)
from app.services.audit.logger import AuditLogger
from app.services.kb.base import KnowledgeBase
from app.services.registry import get_audit_logger, get_knowledge_base

router = APIRouter()


@router.post(
    "/documents",
    response_model=KbDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_document(
    payload: KbDocumentCreate,
    db: AsyncSession = Depends(get_db),
    audit: AuditLogger = Depends(get_audit_logger),
) -> KbDocument:
    doc = KbDocument(
        title=payload.title,
        doc_type=payload.doc_type,
        content=payload.content,
        tags=payload.tags,
        active=payload.active,
    )
    db.add(doc)
    await db.flush()
    await audit.record(
        entity_type="kb_document",
        entity_id=doc.id,
        action="create",
        after={"title": doc.title, "doc_type": doc.doc_type.value},
    )
    await db.commit()
    await db.refresh(doc)
    return doc


@router.get("/documents", response_model=Page[KbDocumentResponse])
async def list_documents(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    doc_type: str | None = Query(None, description="Filter by doc_type enum value"),
    q: str | None = Query(None, description="Keyword match on title + content (ILIKE)"),
    active: bool | None = Query(None, description="Filter by active flag"),
    db: AsyncSession = Depends(get_db),
) -> Page[KbDocumentResponse]:
    base = select(KbDocument)
    count_base = select(func.count()).select_from(KbDocument)

    if doc_type:
        base = base.where(KbDocument.doc_type == doc_type)
        count_base = count_base.where(KbDocument.doc_type == doc_type)
    if active is not None:
        base = base.where(KbDocument.active.is_(active))
        count_base = count_base.where(KbDocument.active.is_(active))
    if q:
        pattern = f"%{q}%"
        base = base.where(
            (KbDocument.title.ilike(pattern)) | (KbDocument.content.ilike(pattern))
        )
        count_base = count_base.where(
            (KbDocument.title.ilike(pattern)) | (KbDocument.content.ilike(pattern))
        )

    total = (await db.execute(count_base)).scalar_one()
    rows = (
        await db.execute(
            base.order_by(KbDocument.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()
    return Page[KbDocumentResponse](
        items=[KbDocumentResponse.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/documents/{doc_id}", response_model=KbDocumentResponse)
async def get_document(doc_id: int, db: AsyncSession = Depends(get_db)) -> KbDocument:
    row = (
        await db.execute(select(KbDocument).where(KbDocument.id == doc_id))
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="document not found")
    return row


@router.put("/documents/{doc_id}", response_model=KbDocumentResponse)
async def update_document(
    doc_id: int,
    payload: KbDocumentUpdate,
    db: AsyncSession = Depends(get_db),
    audit: AuditLogger = Depends(get_audit_logger),
) -> KbDocument:
    doc = (
        await db.execute(select(KbDocument).where(KbDocument.id == doc_id))
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")

    before = {
        "title": doc.title,
        "doc_type": doc.doc_type.value,
        "tags": doc.tags,
        "active": doc.active,
        "version": doc.version,
    }

    patch = payload.model_dump(exclude_unset=True)
    content_changed = "content" in patch and patch["content"] != doc.content

    for key, value in patch.items():
        setattr(doc, key, value)

    # Bump version on any content change so grounded drafts can pin to a snapshot.
    if content_changed:
        doc.version = doc.version + 1

    await db.flush()
    await audit.record(
        entity_type="kb_document",
        entity_id=doc.id,
        action="update",
        before=before,
        after={
            "title": doc.title,
            "doc_type": doc.doc_type.value,
            "tags": doc.tags,
            "active": doc.active,
            "version": doc.version,
        },
    )
    await db.commit()
    await db.refresh(doc)
    return doc


@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    audit: AuditLogger = Depends(get_audit_logger),
) -> None:
    doc = (
        await db.execute(select(KbDocument).where(KbDocument.id == doc_id))
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")

    await audit.record(
        entity_type="kb_document",
        entity_id=doc.id,
        action="delete",
        before={"title": doc.title, "doc_type": doc.doc_type.value},
    )
    await db.delete(doc)
    await db.commit()


@router.post("/search", response_model=list[KbSearchHit])
async def search(
    payload: KbSearchRequest,
    db: AsyncSession = Depends(get_db),
    kb: KnowledgeBase = Depends(get_knowledge_base),
) -> list[KbSearchHit]:
    return await kb.search(
        db=db,
        query=payload.query,
        top_k=payload.top_k,
        doc_types=payload.doc_types,
    )


@router.post("/reindex", status_code=status.HTTP_202_ACCEPTED)
async def reindex() -> dict[str, str]:
    """Placeholder — becomes a real task once chunking + embeddings land (Phase 3)."""
    return {"status": "accepted", "detail": "reindex is a no-op until pgvector support lands"}

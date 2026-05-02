from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.classification import ClassificationResult, ReviewCategory, Sentiment, Urgency
from app.models.kb import KbDocument
from app.models.reply import ReplyDraft, ReplyStatus
from app.models.review import Review
from app.schemas.classification import ClassificationPayload, TopCandidate
from app.schemas.reply import (
    ReplyApproveRequest,
    ReplyDraftResponse,
    ReplyGenerateRequest,
    ReplyRejectRequest,
)
from app.services.audit.logger import AuditLogger
from app.services.generation.base import ReplyGenerator
from app.services.kb.base import KnowledgeBase
from app.services.notifications.base import Notifier
from app.services.notifications.hooks import notify_reply_published
from app.services.registry import (
    get_audit_logger,
    get_knowledge_base,
    get_notifier,
    get_reply_generator,
)

router = APIRouter()


def _to_payload(row: ClassificationResult) -> ClassificationPayload:
    return ClassificationPayload(
        categories=[ReviewCategory(c) for c in row.categories],
        sentiment=Sentiment(row.sentiment),
        urgency=Urgency(row.urgency),
        confidence=row.confidence,
        entropy=row.entropy,
        ambiguity_score=row.ambiguity_score,
        top_candidates=(
            [TopCandidate(**c) for c in row.top_candidates] if row.top_candidates else None
        ),
        needs_clarification=row.needs_clarification,
        out_of_distribution=row.out_of_distribution,
        model_version=row.model_version,
    )


# Category → Korean search seed. Tokens appear in tags/content of the seed
# docs so they act as boost terms on top of the review text itself.
_CATEGORY_QUERY: dict[str, list[str]] = {
    "bug": ["버그", "오류"],
    "payment": ["결제", "구독"],
    "refund": ["환불"],
    "performance": ["느림", "성능"],
    "login_account": ["로그인", "계정"],
    "ux_ui": ["디자인", "UI"],
    "feature_request": ["기능"],
    "policy_inquiry": ["약관", "정책"],
    "complaint": ["불편"],
    "praise": ["감사"],
    "spam": ["스팸"],
    "other": ["문의"],
}


# Clip review text fed into the KB query so the ranker isn't dominated by
# tokens that have nothing to do with the issue.
_REVIEW_SNIPPET_FOR_QUERY = 120


def _build_kb_query(
    classification: ClassificationResult, review_text: str
) -> str:
    """Assemble the search query fed to KB: category seed tokens + top of review text.

    Category tokens come first so they get equal footing with long body tokens
    once `_tokenize` splits on whitespace/punctuation.
    """
    seeds: list[str] = []
    for c in classification.categories:
        seeds.extend(_CATEGORY_QUERY.get(c, [c]))
    head = review_text[:_REVIEW_SNIPPET_FOR_QUERY]
    return " ".join(seeds + [head])


async def _fetch_grounded_docs(
    *,
    kb: KnowledgeBase,
    db: AsyncSession,
    classification: ClassificationResult,
    review_text: str,
) -> tuple[list[KbDocument], list[str]]:
    """Run KB search + hydrate the hit docs from the DB so the LLM polish
    path has actual content to cite.

    Returns (ordered_docs, refs) — refs are the stable "kb:<id>" strings we
    persist into ReplyDraft.grounded_sources.
    """
    if not classification.categories:
        return [], []
    query = _build_kb_query(classification, review_text)
    hits = await kb.search(db=db, query=query, top_k=3)
    if not hits:
        return [], []

    ordered_ids = [h.document_id for h in hits]
    rows = (
        await db.execute(select(KbDocument).where(KbDocument.id.in_(ordered_ids)))
    ).scalars().all()
    by_id = {d.id: d for d in rows}
    docs = [by_id[i] for i in ordered_ids if i in by_id]
    refs = [f"kb:{d.id}" for d in docs]
    return docs, refs


async def _load_review_with_classification(
    db: AsyncSession, review_id: int
) -> tuple[Review, ClassificationResult]:
    review = (
        await db.execute(select(Review).where(Review.id == review_id))
    ).scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="review not found")
    classification = (
        await db.execute(
            select(ClassificationResult).where(ClassificationResult.review_id == review_id)
        )
    ).scalar_one_or_none()
    if not classification:
        raise HTTPException(
            status_code=409, detail="classify the review first (POST /classify/{review_id})"
        )
    return review, classification


async def _generate_and_persist(
    *,
    review: Review,
    classification: ClassificationResult,
    payload: ReplyGenerateRequest,
    db: AsyncSession,
    generator: ReplyGenerator,
    kb: KnowledgeBase,
    overwrite: bool,
) -> tuple[ReplyDraft, str]:
    grounded_docs: list[KbDocument] = []
    grounded_sources: list[str] | None = None
    if payload.ground_with_kb:
        grounded_docs, refs = await _fetch_grounded_docs(
            kb=kb,
            db=db,
            classification=classification,
            review_text=review.normalized_text,
        )
        grounded_sources = refs or None

    generated = await generator.generate(
        classification=_to_payload(classification),
        review_text=review.normalized_text,
        tone=payload.tone,
        template_id=payload.template_id,
        grounded_docs=grounded_docs or None,
    )

    existing = (
        await db.execute(select(ReplyDraft).where(ReplyDraft.review_id == review.id))
    ).scalar_one_or_none()

    if existing and not overwrite:
        raise HTTPException(status_code=409, detail="draft already exists; use /regenerate")

    if existing:
        existing.tone = generated.tone
        existing.template_id = generated.template_id
        existing.generated_text = generated.text
        existing.model_version = generated.model_version
        existing.requires_human_approval = generated.requires_human_approval
        existing.grounded_sources = grounded_sources
        existing.status = ReplyStatus.PENDING
        existing.approved_by = None
        existing.approved_at = None
        existing.published_at = None
        draft = existing
        action_label = "regenerate"
    else:
        draft = ReplyDraft(
            review_id=review.id,
            tone=generated.tone,
            template_id=generated.template_id,
            generated_text=generated.text,
            requires_human_approval=generated.requires_human_approval,
            model_version=generated.model_version,
            grounded_sources=grounded_sources,
            status=ReplyStatus.PENDING,
        )
        db.add(draft)
        action_label = "generate"
    return draft, action_label


@router.post(
    "/generate/{review_id}",
    response_model=ReplyDraftResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate(
    review_id: int,
    payload: ReplyGenerateRequest | None = None,
    db: AsyncSession = Depends(get_db),
    generator: ReplyGenerator = Depends(get_reply_generator),
    kb: KnowledgeBase = Depends(get_knowledge_base),
    audit: AuditLogger = Depends(get_audit_logger),
) -> ReplyDraft:
    review, classification = await _load_review_with_classification(db, review_id)
    draft, action_label = await _generate_and_persist(
        review=review,
        classification=classification,
        payload=payload or ReplyGenerateRequest(),
        db=db,
        generator=generator,
        kb=kb,
        overwrite=False,
    )
    await db.flush()
    await audit.record(
        entity_type="reply_draft",
        entity_id=draft.id,
        action=action_label,
        after={
            "template_id": draft.template_id,
            "tone": draft.tone.value,
            "model_version": draft.model_version,
            "requires_human_approval": draft.requires_human_approval,
            "grounded_sources": draft.grounded_sources,
        },
    )
    await db.commit()
    await db.refresh(draft)
    return draft


@router.post("/regenerate/{review_id}", response_model=ReplyDraftResponse)
async def regenerate(
    review_id: int,
    payload: ReplyGenerateRequest | None = None,
    db: AsyncSession = Depends(get_db),
    generator: ReplyGenerator = Depends(get_reply_generator),
    kb: KnowledgeBase = Depends(get_knowledge_base),
    audit: AuditLogger = Depends(get_audit_logger),
) -> ReplyDraft:
    review, classification = await _load_review_with_classification(db, review_id)
    draft, action_label = await _generate_and_persist(
        review=review,
        classification=classification,
        payload=payload or ReplyGenerateRequest(),
        db=db,
        generator=generator,
        kb=kb,
        overwrite=True,
    )
    await db.flush()
    await audit.record(
        entity_type="reply_draft",
        entity_id=draft.id,
        action=action_label,
        after={
            "template_id": draft.template_id,
            "tone": draft.tone.value,
            "model_version": draft.model_version,
            "grounded_sources": draft.grounded_sources,
        },
    )
    await db.commit()
    await db.refresh(draft)
    return draft


async def _load_draft(db: AsyncSession, review_id: int) -> ReplyDraft:
    draft = (
        await db.execute(select(ReplyDraft).where(ReplyDraft.review_id == review_id))
    ).scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=404, detail="reply draft not found")
    return draft


@router.post("/{review_id}/approve", response_model=ReplyDraftResponse)
async def approve(
    review_id: int,
    payload: ReplyApproveRequest,
    db: AsyncSession = Depends(get_db),
    audit: AuditLogger = Depends(get_audit_logger),
) -> ReplyDraft:
    draft = await _load_draft(db, review_id)
    if draft.status in (ReplyStatus.REJECTED, ReplyStatus.PUBLISHED):
        raise HTTPException(status_code=409, detail=f"draft already {draft.status.value}")

    before = {"status": draft.status.value, "generated_text": draft.generated_text}
    if payload.edited_text is not None:
        draft.generated_text = payload.edited_text
    draft.status = ReplyStatus.APPROVED
    draft.approved_at = datetime.now(timezone.utc)
    # TODO: bind approver once auth dep is in place.
    await audit.record(
        entity_type="reply_draft",
        entity_id=draft.id,
        action="approve",
        before=before,
        after={"status": draft.status.value, "generated_text": draft.generated_text},
    )
    await db.commit()
    await db.refresh(draft)
    return draft


@router.post("/{review_id}/reject", response_model=ReplyDraftResponse)
async def reject(
    review_id: int,
    payload: ReplyRejectRequest,
    db: AsyncSession = Depends(get_db),
    audit: AuditLogger = Depends(get_audit_logger),
) -> ReplyDraft:
    draft = await _load_draft(db, review_id)
    if draft.status == ReplyStatus.PUBLISHED:
        raise HTTPException(status_code=409, detail="cannot reject a published draft")
    before = {"status": draft.status.value}
    draft.status = ReplyStatus.REJECTED
    await audit.record(
        entity_type="reply_draft",
        entity_id=draft.id,
        action="reject",
        before=before,
        after={"status": draft.status.value},
        reason=payload.reason,
    )
    await db.commit()
    await db.refresh(draft)
    return draft


@router.post("/{review_id}/publish", response_model=ReplyDraftResponse)
async def publish(
    review_id: int,
    db: AsyncSession = Depends(get_db),
    audit: AuditLogger = Depends(get_audit_logger),
    notifier: Notifier = Depends(get_notifier),
) -> ReplyDraft:
    draft = await _load_draft(db, review_id)
    if draft.status != ReplyStatus.APPROVED:
        raise HTTPException(status_code=409, detail="only approved drafts may be published")
    before = {"status": draft.status.value}
    draft.status = ReplyStatus.PUBLISHED
    draft.published_at = datetime.now(timezone.utc)
    await audit.record(
        entity_type="reply_draft",
        entity_id=draft.id,
        action="publish",
        before=before,
        after={"status": draft.status.value},
    )
    # NOTE: actually pushing to the store (Google Play / App Store) is deferred
    # to a publisher worker — this endpoint only records intent + audit trail.
    await db.commit()
    await db.refresh(draft)

    review = (
        await db.execute(select(Review).where(Review.id == review_id))
    ).scalar_one_or_none()
    if review is not None:
        await notify_reply_published(notifier=notifier, review=review, draft=draft)
    return draft

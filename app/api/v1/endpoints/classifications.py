from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.dependencies import get_db
from app.models.classification import (
    ClassificationResult,
    ReviewCategory,
    Sentiment,
    Urgency,
)
from app.models.policy import PolicyDecision
from app.models.review import Review
from app.schemas.classification import (
    ClarifyRequest,
    ClassificationPayload,
    ClassificationResponse,
    ShadowCompareResponse,
    TopCandidate,
)
from app.services.audit.logger import AuditLogger
from app.services.classification.base import Classifier
from app.services.classification.scoring import compute_from_candidates
from app.services.classification.stub import StubClassifier
from app.services.policy.base import PolicyEngine
from app.services.registry import get_audit_logger, get_classifier, get_policy_engine

router = APIRouter()


@router.post(
    "/classify/{review_id}",
    response_model=ClassificationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def classify_review(
    review_id: int,
    db: AsyncSession = Depends(get_db),
    classifier: Classifier = Depends(get_classifier),
    audit: AuditLogger = Depends(get_audit_logger),
) -> ClassificationResult:
    review = (
        await db.execute(select(Review).where(Review.id == review_id))
    ).scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="review not found")

    existing = (
        await db.execute(
            select(ClassificationResult).where(ClassificationResult.review_id == review_id)
        )
    ).scalar_one_or_none()

    payload = await classifier.classify(
        review_text=review.normalized_text, review_id=review_id
    )

    if existing:
        existing.categories = [c.value for c in payload.categories]
        existing.sentiment = payload.sentiment
        existing.urgency = payload.urgency
        existing.confidence = payload.confidence
        existing.entropy = payload.entropy
        existing.ambiguity_score = payload.ambiguity_score
        existing.top_candidates = (
            [c.model_dump() for c in payload.top_candidates] if payload.top_candidates else None
        )
        existing.needs_clarification = payload.needs_clarification
        existing.out_of_distribution = payload.out_of_distribution
        existing.model_version = payload.model_version
        row = existing
        action = "reclassify"
    else:
        row = ClassificationResult(
            review_id=review_id,
            categories=[c.value for c in payload.categories],
            sentiment=payload.sentiment,
            urgency=payload.urgency,
            confidence=payload.confidence,
            entropy=payload.entropy,
            ambiguity_score=payload.ambiguity_score,
            top_candidates=(
                [c.model_dump() for c in payload.top_candidates]
                if payload.top_candidates
                else None
            ),
            needs_clarification=payload.needs_clarification,
            out_of_distribution=payload.out_of_distribution,
            model_version=payload.model_version,
        )
        db.add(row)
        action = "classify"

    await db.flush()
    await audit.record(
        entity_type="classification_result",
        entity_id=row.id,
        action=action,
        after={
            "categories": row.categories,
            "sentiment": row.sentiment.value,
            "urgency": row.urgency.value,
            "confidence": row.confidence,
            "entropy": row.entropy,
            "ambiguity_score": row.ambiguity_score,
            "model_version": row.model_version,
        },
    )
    await db.commit()
    await db.refresh(row)
    return row


@router.get("/classifications/{review_id}", response_model=ClassificationResponse)
async def get_classification(
    review_id: int, db: AsyncSession = Depends(get_db)
) -> ClassificationResult:
    row = (
        await db.execute(
            select(ClassificationResult).where(ClassificationResult.review_id == review_id)
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="classification not found")
    return row


@router.post(
    "/classify/{review_id}/compare",
    response_model=ShadowCompareResponse,
)
async def classify_compare(
    review_id: int,
    db: AsyncSession = Depends(get_db),
) -> ShadowCompareResponse:
    """Run stub + LLM classifiers in parallel; don't persist either result.

    Lets the operator A/B compare what the heuristic stub vs the LLM would
    emit for the same review text. Returns `llm_error` when the LLM path
    can't run (no API key, model 404, etc) instead of 500-ing — the stub
    result is always usable.
    """
    review = (
        await db.execute(select(Review).where(Review.id == review_id))
    ).scalar_one_or_none()
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")

    stub = StubClassifier()
    stub_payload = await stub.classify(
        review_text=review.normalized_text, review_id=review_id
    )

    llm_payload: ClassificationPayload | None = None
    llm_error: str | None = None
    if settings.OPENAI_API_KEY:
        try:
            from openai import AsyncOpenAI

            from app.services.classification.llm import OpenAiClassifier

            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            llm = OpenAiClassifier(
                client=client, model=settings.OPENAI_CLASSIFIER_MODEL
            )
            llm_payload = await llm.classify(
                review_text=review.normalized_text, review_id=review_id
            )
        except Exception as e:  # noqa: BLE001 — propagate to UI
            llm_error = f"{type(e).__name__}: {e}"
    else:
        llm_error = "OPENAI_API_KEY not configured"

    return ShadowCompareResponse(
        stub=stub_payload, llm=llm_payload, llm_error=llm_error
    )


@router.post(
    "/classify/{review_id}/clarify",
    response_model=ClassificationResponse,
)
async def clarify(
    review_id: int,
    payload: ClarifyRequest,
    db: AsyncSession = Depends(get_db),
    engine: PolicyEngine = Depends(get_policy_engine),
    audit: AuditLogger = Depends(get_audit_logger),
) -> ClassificationResult:
    """Operator override after REQUEST_CLARIFICATION: pin categories, clear the
    needs_clarification flag, and rerun the policy engine so the review
    unblocks. Both the classification and the new policy decision are audit
    logged as `clarify` / `re_evaluate_after_clarify`.
    """
    review = (
        await db.execute(select(Review).where(Review.id == review_id))
    ).scalar_one_or_none()
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")

    classif = (
        await db.execute(
            select(ClassificationResult).where(ClassificationResult.review_id == review_id)
        )
    ).scalar_one_or_none()
    if classif is None:
        raise HTTPException(status_code=404, detail="classification not found")

    before = {
        "categories": list(classif.categories),
        "needs_clarification": classif.needs_clarification,
    }

    classif.categories = [c.value for c in payload.categories]
    classif.needs_clarification = False
    # Recompute ambiguity now that the category is pinned (margin/entropy are
    # effectively 0 for a single hand-picked label). We keep confidence as-is
    # so downstream can still see the classifier's original certainty.
    entropy_norm, ambiguity = compute_from_candidates(
        top1_confidence=classif.confidence,
        top_candidates=None,
        is_ood=classif.out_of_distribution,
    )
    classif.entropy = round(entropy_norm, 4)
    classif.ambiguity_score = round(ambiguity, 4)

    await db.flush()
    await audit.record(
        entity_type="classification_result",
        entity_id=classif.id,
        action="clarify",
        before=before,
        after={
            "categories": classif.categories,
            "needs_clarification": classif.needs_clarification,
            "ambiguity_score": classif.ambiguity_score,
        },
        reason=payload.reason,
    )

    # Rerun policy with the pinned categories.
    cls_payload = ClassificationPayload(
        categories=[ReviewCategory(c) for c in classif.categories],
        sentiment=Sentiment(classif.sentiment),
        urgency=Urgency(classif.urgency),
        confidence=classif.confidence,
        entropy=classif.entropy,
        ambiguity_score=classif.ambiguity_score,
        top_candidates=(
            [TopCandidate(**c) for c in classif.top_candidates]
            if classif.top_candidates
            else None
        ),
        needs_clarification=False,
        out_of_distribution=classif.out_of_distribution,
        model_version=classif.model_version,
    )
    new_decision = await engine.evaluate(
        classification=cls_payload,
        rating=review.rating,
        app_version=review.app_version,
    )

    existing_decision = (
        await db.execute(
            select(PolicyDecision).where(PolicyDecision.review_id == review_id)
        )
    ).scalar_one_or_none()
    pd_before = (
        {
            "action": existing_decision.action.value,
            "risk_score": existing_decision.risk_score,
            "reason_codes": existing_decision.reason_codes,
        }
        if existing_decision
        else None
    )
    if existing_decision is None:
        existing_decision = PolicyDecision(
            review_id=review_id,
            action=new_decision.action,
            risk_score=new_decision.risk_score,
            reason_codes=new_decision.reason_codes,
            policy_version=new_decision.policy_version,
        )
        db.add(existing_decision)
    else:
        existing_decision.action = new_decision.action
        existing_decision.risk_score = new_decision.risk_score
        existing_decision.reason_codes = new_decision.reason_codes
        existing_decision.policy_version = new_decision.policy_version
    await db.flush()
    await audit.record(
        entity_type="policy_decision",
        entity_id=existing_decision.id,
        action="re_evaluate_after_clarify",
        before=pd_before,
        after={
            "action": existing_decision.action.value,
            "risk_score": existing_decision.risk_score,
            "reason_codes": existing_decision.reason_codes,
        },
    )

    await db.commit()
    await db.refresh(classif)
    return classif

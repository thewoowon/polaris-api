from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.classification import ClassificationResult, ReviewCategory, Sentiment, Urgency
from app.models.policy import PolicyDecision
from app.models.review import Review
from app.schemas.classification import ClassificationPayload, TopCandidate
from app.schemas.policy import PolicyDecisionResponse
from pydantic import BaseModel, Field

from app.services.audit.logger import AuditLogger
from app.services.notifications.base import Notifier
from app.services.notifications.hooks import notify_policy_decision
from app.services.policy.base import PolicyEngine
from app.services.policy.yaml_engine import (
    PolicyRulesError,
    YamlPolicyEngine,
    load_rules_doc,
)
from app.services.registry import get_audit_logger, get_notifier, get_policy_engine

router = APIRouter()


@router.get("/rules")
def get_rules(engine: PolicyEngine = Depends(get_policy_engine)) -> dict:
    """Return the currently loaded policy rule set (read-only).

    Useful for operators to see what rules are active without shelling into
    the host. Edit `app/services/policy/rules.yaml` + restart uvicorn to
    modify.
    """
    if not isinstance(engine, YamlPolicyEngine):
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="current policy engine does not expose a rules document",
        )
    return engine.rules_doc


class _RulesYamlBody(BaseModel):
    yaml: str = Field(..., min_length=1)


def _yaml_engine_or_501(engine: PolicyEngine) -> YamlPolicyEngine:
    if not isinstance(engine, YamlPolicyEngine):
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="current policy engine is not YAML-backed",
        )
    return engine


@router.get("/rules/raw")
def get_rules_raw(engine: PolicyEngine = Depends(get_policy_engine)) -> dict:
    """Return the raw YAML text so an editor UI can round-trip edits."""
    yaml_engine = _yaml_engine_or_501(engine)
    path = yaml_engine.rules_path
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"cannot read rules file: {e}")
    return {"path": str(path), "yaml": raw}


@router.post("/rules/validate")
def validate_rules(
    payload: _RulesYamlBody, engine: PolicyEngine = Depends(get_policy_engine)
) -> dict:
    """Parse + validate YAML without touching the engine or disk.

    Useful for a preview button in the editor UI.
    """
    _yaml_engine_or_501(engine)
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        f.write(payload.yaml)
        tmp_path = f.name
    try:
        from pathlib import Path as _P

        doc = load_rules_doc(_P(tmp_path))
    except PolicyRulesError as e:
        raise HTTPException(status_code=422, detail=str(e))
    finally:
        import os

        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    return {"ok": True, "rule_count": len(doc["rules"]), "version": doc.get("version")}


@router.put("/rules/raw")
async def put_rules_raw(
    payload: _RulesYamlBody,
    engine: PolicyEngine = Depends(get_policy_engine),
    audit: AuditLogger = Depends(get_audit_logger),
) -> dict:
    """Validate → write to rules.yaml → reload the engine. Atomic: if
    validation fails, nothing is written and the old ruleset stays active.
    """
    yaml_engine = _yaml_engine_or_501(engine)
    path = yaml_engine.rules_path

    import tempfile
    from pathlib import Path as _P

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        f.write(payload.yaml)
        tmp_path = f.name
    try:
        doc = load_rules_doc(_P(tmp_path))
    except PolicyRulesError as e:
        import os

        os.unlink(tmp_path)
        raise HTTPException(status_code=422, detail=str(e))

    # Snapshot the previous rule file for audit + rollback.
    try:
        previous = path.read_text(encoding="utf-8")
    except OSError:
        previous = None

    try:
        path.write_text(payload.yaml, encoding="utf-8")
    except OSError as e:
        import os

        os.unlink(tmp_path)
        raise HTTPException(status_code=500, detail=f"cannot write rules file: {e}")

    import os

    os.unlink(tmp_path)

    yaml_engine.reload()
    await audit.record(
        entity_type="policy_rules",
        entity_id=None,
        action="update",
        before={"yaml": (previous[:500] + "…") if previous and len(previous) > 500 else previous},
        after={
            "version": doc.get("version"),
            "rule_count": len(doc["rules"]),
        },
    )
    return {"ok": True, "rule_count": len(doc["rules"]), "version": doc.get("version")}


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


@router.post(
    "/evaluate/{review_id}",
    response_model=PolicyDecisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def evaluate_policy(
    review_id: int,
    db: AsyncSession = Depends(get_db),
    engine: PolicyEngine = Depends(get_policy_engine),
    audit: AuditLogger = Depends(get_audit_logger),
    notifier: Notifier = Depends(get_notifier),
) -> PolicyDecision:
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
            status_code=409,
            detail="classify the review first (POST /classify/{review_id})",
        )

    result = await engine.evaluate(
        classification=_to_payload(classification),
        rating=review.rating,
        app_version=review.app_version,
    )

    existing = (
        await db.execute(select(PolicyDecision).where(PolicyDecision.review_id == review_id))
    ).scalar_one_or_none()
    if existing:
        existing.action = result.action
        existing.risk_score = result.risk_score
        existing.reason_codes = result.reason_codes
        existing.policy_version = result.policy_version
        row = existing
        action_label = "re_evaluate"
    else:
        row = PolicyDecision(
            review_id=review_id,
            action=result.action,
            risk_score=result.risk_score,
            reason_codes=result.reason_codes,
            policy_version=result.policy_version,
        )
        db.add(row)
        action_label = "evaluate"

    await db.flush()
    await audit.record(
        entity_type="policy_decision",
        entity_id=row.id,
        action=action_label,
        after={
            "action": row.action.value,
            "risk_score": row.risk_score,
            "reason_codes": row.reason_codes,
            "policy_version": row.policy_version,
        },
    )
    await db.commit()
    await db.refresh(row)
    await notify_policy_decision(notifier=notifier, review=review, decision=row)
    return row


@router.get("/decisions/{review_id}", response_model=PolicyDecisionResponse)
async def get_decision(
    review_id: int, db: AsyncSession = Depends(get_db)
) -> PolicyDecision:
    row = (
        await db.execute(
            select(PolicyDecision).where(PolicyDecision.review_id == review_id)
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="policy decision not found")
    return row

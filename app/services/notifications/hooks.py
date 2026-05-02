"""Helpers that decide WHEN to notify based on settings + event type.

Keeps the notify-or-not decision out of every call site so endpoints stay
boring. Each hook catches its own Notifier errors defensively.
"""

from __future__ import annotations

import logging

from app.core.config import settings
from app.models.policy import PolicyAction, PolicyDecision
from app.models.reply import ReplyDraft
from app.models.review import Review
from app.services.notifications.base import Notification, Notifier, Severity


logger = logging.getLogger(__name__)


def _configured_actions() -> set[str]:
    raw = (settings.NOTIFY_POLICY_ACTIONS or "").strip()
    if raw == "*":
        return {a.value for a in PolicyAction}
    return {s.strip() for s in raw.split(",") if s.strip()}


_ACTION_SEVERITY: dict[PolicyAction, Severity] = {
    PolicyAction.CREATE_ISSUE: Severity.CRITICAL,
    PolicyAction.ROUTE_TO_HUMAN: Severity.WARNING,
    PolicyAction.REQUEST_CLARIFICATION: Severity.WARNING,
    PolicyAction.DRAFT_REPLY: Severity.INFO,
    PolicyAction.AUTO_REPLY: Severity.INFO,
    PolicyAction.IGNORE: Severity.INFO,
}


async def notify_policy_decision(
    *,
    notifier: Notifier,
    review: Review,
    decision: PolicyDecision,
) -> None:
    """Fire if the resolved action is in NOTIFY_POLICY_ACTIONS."""
    if decision.action.value not in _configured_actions():
        return

    severity = _ACTION_SEVERITY.get(decision.action, Severity.INFO)
    excerpt = review.normalized_text[:160]
    try:
        await notifier.notify(
            Notification(
                title=f"[policy:{decision.action.value}] review #{review.id}",
                message=excerpt,
                severity=severity,
                entity=f"review:{review.id}",
                extra={
                    "risk_score": decision.risk_score,
                    "reason_codes": ",".join(decision.reason_codes[:3]),
                    "source": review.source.value,
                    "rating": review.rating,
                },
            )
        )
    except Exception as e:  # noqa: BLE001 — notifier outage must not poison caller
        logger.warning("notify_policy_decision failed: %s", e)


async def notify_reply_published(
    *,
    notifier: Notifier,
    review: Review,
    draft: ReplyDraft,
) -> None:
    if not settings.NOTIFY_ON_PUBLISH:
        return
    try:
        await notifier.notify(
            Notification(
                title=f"[reply:published] review #{review.id}",
                message=draft.generated_text[:200],
                severity=Severity.INFO,
                entity=f"review:{review.id}",
                extra={
                    "template_id": draft.template_id,
                    "model_version": draft.model_version,
                },
            )
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("notify_reply_published failed: %s", e)

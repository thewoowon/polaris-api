from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.models.classification import ReviewCategory
from app.models.reply import ReplyTone
from app.schemas.classification import ClassificationPayload
from app.services.generation.templates import pick_template

if TYPE_CHECKING:
    from app.models.kb import KbDocument


@dataclass
class _GeneratedReply:
    tone: ReplyTone
    template_id: str | None
    text: str
    model_version: str | None
    requires_human_approval: bool


HIGH_RISK_CATEGORIES = {
    ReviewCategory.PAYMENT,
    ReviewCategory.REFUND,
    ReviewCategory.LOGIN_ACCOUNT,
}


def requires_human_for(categories) -> bool:
    """Shared truth for "this draft must not auto-publish" (blueprint §20)."""
    return bool(set(categories) & HIGH_RISK_CATEGORIES)


class TemplateReplyGenerator:
    """Template-only generator — no LLM call.

    Blueprint §11.1: template → slot fill → (optional LLM polish) → policy
    check. For Phase 1 we stop after slot fill so we can ship without an LLM
    integration. LLM-backed generator (LlmPolishedReplyGenerator) extends
    this by polishing `text` against the template + grounded docs.
    """

    model_version = "templates-v1"

    async def generate(
        self,
        *,
        classification: ClassificationPayload,
        review_text: str,
        tone: ReplyTone = ReplyTone.FORMAL,
        template_id: str | None = None,
        grounded_docs: "list[KbDocument] | None" = None,  # unused by template path
    ) -> _GeneratedReply:
        template = pick_template(list(classification.categories))
        return _GeneratedReply(
            tone=tone,
            template_id=template.id,
            text=template.text,
            model_version=self.model_version,
            requires_human_approval=requires_human_for(classification.categories),
        )

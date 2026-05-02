from typing import TYPE_CHECKING, Protocol

from app.models.reply import ReplyTone
from app.schemas.classification import ClassificationPayload

if TYPE_CHECKING:
    from app.models.kb import KbDocument


class GeneratedReply(Protocol):
    tone: ReplyTone
    template_id: str | None
    text: str
    model_version: str | None
    requires_human_approval: bool


class ReplyGenerator(Protocol):
    """Template-first, LLM-optional (blueprint §11.1).

    Generators MUST NOT free-form. The contract is: pick a template, fill
    slots, optionally run an LLM polish using `grounded_docs`, and return a
    structured result. The `requires_human_approval` flag must respect the
    high-risk category rules regardless of what the LLM produces.
    """

    async def generate(
        self,
        *,
        classification: ClassificationPayload,
        review_text: str,
        tone: ReplyTone = ReplyTone.FORMAL,
        template_id: str | None = None,
        grounded_docs: "list[KbDocument] | None" = None,
    ) -> GeneratedReply: ...

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.reply import ReplyStatus, ReplyTone
from app.schemas.common import ORMModel


class ReplyGenerateRequest(BaseModel):
    tone: ReplyTone = ReplyTone.FORMAL
    template_id: str | None = None
    ground_with_kb: bool = False


class ReplyDraftResponse(ORMModel):
    id: int
    review_id: int
    tone: ReplyTone
    template_id: str | None
    grounded_sources: list[str] | None
    generated_text: str
    requires_human_approval: bool
    model_version: str | None
    status: ReplyStatus
    approved_by: int | None
    approved_at: datetime | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ReplyApproveRequest(BaseModel):
    edited_text: str | None = Field(
        None, description="If present, replaces generated_text before publish."
    )


class ReplyRejectRequest(BaseModel):
    reason: str

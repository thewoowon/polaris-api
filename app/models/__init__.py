"""Explicit model imports so Base.metadata sees every table during Alembic runs."""

from app.models.audit import AuditLog
from app.models.classification import (
    ClassificationResult,
    ReviewCategory,
    Sentiment,
    Urgency,
)
from app.models.kb import DocType, KbChunk, KbDocument
from app.models.policy import PolicyAction, PolicyDecision
from app.models.reply import ReplyDraft, ReplyStatus, ReplyTone
from app.models.review import Review, ReviewSource
from app.models.token import Token
from app.models.user import User, UserRole

__all__ = [
    "AuditLog",
    "ClassificationResult",
    "DocType",
    "KbChunk",
    "KbDocument",
    "PolicyAction",
    "PolicyDecision",
    "ReplyDraft",
    "ReplyStatus",
    "ReplyTone",
    "Review",
    "ReviewCategory",
    "ReviewSource",
    "Sentiment",
    "Token",
    "Urgency",
    "User",
    "UserRole",
]

"""Explicit model imports so Base.metadata sees every table during Alembic runs."""

from app.models.app_benchmark import AppBenchmark
from app.models.app_profile import AppProfile, Platform
from app.models.audit import AuditLog
from app.models.classification import (
    ClassificationResult,
    ReviewCategory,
    Sentiment,
    Urgency,
)
from app.models.kb import DocType, KbChunk, KbDocument
from app.models.policy import PolicyAction, PolicyDecision
from app.models.company import Company, Industry
from app.models.insight import Insight, InsightType, InsightSeverity, BusinessImpact
from app.models.reply import ReplyDraft, ReplyStatus, ReplyTone
from app.models.report import Report, ReportType, ReportStatus
from app.models.review import Review, ReviewSource
from app.models.review_cluster import ReviewCluster, IssueType, ClusterSeverity
from app.models.token import Token
from app.models.user import User, UserRole

__all__ = [
    "AppBenchmark",
    "AppProfile",
    "AuditLog",
    "BusinessImpact",
    "ClassificationResult",
    "ClusterSeverity",
    "Company",
    "DocType",
    "Industry",
    "Insight",
    "InsightSeverity",
    "InsightType",
    "IssueType",
    "KbChunk",
    "KbDocument",
    "Platform",
    "PolicyAction",
    "PolicyDecision",
    "ReplyDraft",
    "ReplyStatus",
    "ReplyTone",
    "Report",
    "ReportStatus",
    "ReportType",
    "Review",
    "ReviewCategory",
    "ReviewCluster",
    "ReviewSource",
    "Sentiment",
    "Token",
    "Urgency",
    "User",
    "UserRole",
]

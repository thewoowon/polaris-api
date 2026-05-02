"""Service-to-implementation bindings. Routes depend on these factories, not
concrete classes, so we can swap an LLM-backed classifier or a pgvector KB
without touching routes."""

from __future__ import annotations

import logging

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.dependencies import get_db
from app.services.audit.logger import AuditLogger
from app.services.classification.base import Classifier
from app.services.classification.stub import StubClassifier
from app.services.generation.base import ReplyGenerator
from app.services.generation.default import TemplateReplyGenerator
from app.services.kb.base import KnowledgeBase
from app.services.kb.keyword import KeywordKnowledgeBase
from app.services.notifications.base import Notifier
from app.services.notifications.console import ConsoleNotifier
from app.services.notifications.fanout import FanoutNotifier
from app.services.notifications.slack import SlackWebhookNotifier
from app.services.policy.base import PolicyEngine
from app.services.policy.engine import RuleBasedPolicyEngine

logger = logging.getLogger(__name__)


def _build_classifier() -> Classifier:
    """OpenAI-backed when OPENAI_API_KEY is set; otherwise a deterministic stub."""
    if not settings.OPENAI_API_KEY:
        logger.info("OPENAI_API_KEY not set — using StubClassifier")
        return StubClassifier()
    try:
        from openai import AsyncOpenAI

        from app.services.classification.llm import OpenAiClassifier

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        logger.info("Using OpenAiClassifier with model=%s", settings.OPENAI_CLASSIFIER_MODEL)
        return OpenAiClassifier(client=client, model=settings.OPENAI_CLASSIFIER_MODEL)
    except Exception as e:  # pragma: no cover — defensive init
        logger.warning("OpenAiClassifier init failed, falling back to stub: %s", e)
        return StubClassifier()


def _build_reply_generator() -> ReplyGenerator:
    """Template by default; LLM-polish when REPLY_GENERATOR=llm + API key available."""
    template_gen = TemplateReplyGenerator()
    if settings.REPLY_GENERATOR != "llm":
        logger.info("REPLY_GENERATOR=template — using TemplateReplyGenerator")
        return template_gen
    if not settings.OPENAI_API_KEY:
        logger.warning(
            "REPLY_GENERATOR=llm but OPENAI_API_KEY unset — using TemplateReplyGenerator"
        )
        return template_gen
    try:
        from openai import AsyncOpenAI

        from app.services.generation.llm import LlmPolishedReplyGenerator

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        logger.info(
            "REPLY_GENERATOR=llm — polishing templates via %s",
            settings.OPENAI_CLASSIFIER_MODEL,
        )
        return LlmPolishedReplyGenerator(
            client=client,
            model=settings.OPENAI_CLASSIFIER_MODEL,
            fallback=template_gen,
        )
    except Exception as e:  # pragma: no cover — defensive init
        logger.warning("LLM reply generator init failed (%s) — using template", e)
        return template_gen


def _build_notifier() -> Notifier:
    """Console notifier always on; Slack bolted on when webhook URL is set."""
    backends: list[Notifier] = [ConsoleNotifier()]
    if settings.NOTIFY_SLACK_WEBHOOK_URL:
        backends.append(
            SlackWebhookNotifier(webhook_url=settings.NOTIFY_SLACK_WEBHOOK_URL)
        )
        logger.info("notifications: console + slack webhook")
    else:
        logger.info("notifications: console only (no Slack webhook configured)")
    return FanoutNotifier(backends)


# Module-level singletons — stateless impls, safe to share across requests.
_classifier: Classifier = _build_classifier()
_policy: PolicyEngine = RuleBasedPolicyEngine()
_generator: ReplyGenerator = _build_reply_generator()
_kb: KnowledgeBase = KeywordKnowledgeBase()
_notifier: Notifier = _build_notifier()


def get_classifier() -> Classifier:
    return _classifier


def get_policy_engine() -> PolicyEngine:
    return _policy


def get_reply_generator() -> ReplyGenerator:
    return _generator


def get_knowledge_base() -> KnowledgeBase:
    return _kb


def get_notifier() -> Notifier:
    return _notifier


async def get_audit_logger(db: AsyncSession = Depends(get_db)) -> AuditLogger:
    # TODO: resolve actor from auth dep once RBAC lands; for now tag as 'system'.
    return AuditLogger(db=db, actor="system")

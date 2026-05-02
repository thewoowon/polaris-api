import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.services.classification.base import Classifier
from app.services.classification.stub import StubClassifier
from app.services.ingestion.app_store import AppStoreSource
from app.services.ingestion.google_play import GooglePlaySource
from app.services.ingestion.scheduler import init_scheduler
from app.services.ingestion.synthetic import SyntheticSource
from app.services.policy.base import PolicyEngine
from app.services.policy.engine import RuleBasedPolicyEngine


logger = logging.getLogger(__name__)


def _build_sources() -> list:
    """Parse INGESTION_SOURCES into concrete source instances.

    Sources missing their required config (e.g. empty app id) are skipped
    with a warning so the rest of the pipeline still starts.
    """
    names = [s.strip() for s in settings.INGESTION_SOURCES.split(",") if s.strip()]
    sources: list = []
    for name in names:
        if name == "synthetic":
            sources.append(SyntheticSource())
        elif name == "google_play":
            if not settings.INGESTION_GOOGLE_PLAY_APP_ID:
                logger.warning(
                    "google_play source requested but INGESTION_GOOGLE_PLAY_APP_ID is empty — skipping"
                )
                continue
            sources.append(
                GooglePlaySource(
                    app_id=settings.INGESTION_GOOGLE_PLAY_APP_ID,
                    lang=settings.INGESTION_GOOGLE_PLAY_LANG,
                    country=settings.INGESTION_GOOGLE_PLAY_COUNTRY,
                    count=settings.INGESTION_GOOGLE_PLAY_COUNT,
                )
            )
        elif name == "app_store":
            if not settings.INGESTION_APP_STORE_APP_ID:
                logger.warning(
                    "app_store source requested but INGESTION_APP_STORE_APP_ID is empty — skipping"
                )
                continue
            sources.append(
                AppStoreSource(
                    app_id=settings.INGESTION_APP_STORE_APP_ID,
                    country=settings.INGESTION_APP_STORE_COUNTRY,
                )
            )
        else:
            logger.warning("unknown ingestion source %r; skipping", name)
    return sources


def _build_auto_classifier() -> Classifier | None:
    """Pick the classifier for auto-pipeline. Falls back to stub on config/key issues."""
    name = (settings.INGESTION_AUTO_CLASSIFIER or "stub").strip().lower()
    if name == "stub":
        return StubClassifier()
    if name == "openai":
        if not settings.OPENAI_API_KEY:
            logger.warning(
                "INGESTION_AUTO_CLASSIFIER=openai but OPENAI_API_KEY unset — using stub"
            )
            return StubClassifier()
        try:
            from openai import AsyncOpenAI

            from app.services.classification.llm import OpenAiClassifier

            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            return OpenAiClassifier(
                client=client, model=settings.OPENAI_CLASSIFIER_MODEL
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("OpenAI classifier init failed (%s) — using stub", e)
            return StubClassifier()
    logger.warning("unknown INGESTION_AUTO_CLASSIFIER=%r — using stub", name)
    return StubClassifier()


@asynccontextmanager
async def lifespan(app: FastAPI):
    classifier: Classifier | None = None
    policy_engine: PolicyEngine | None = None
    if settings.INGESTION_AUTO_PIPELINE:
        classifier = _build_auto_classifier()
        policy_engine = RuleBasedPolicyEngine()

    # Scheduler is always initialised so POST /ingestion/run stays usable
    # regardless of INGESTION_ENABLED (manual trigger path).
    scheduler = init_scheduler(
        sources=_build_sources(),
        interval_sec=settings.INGESTION_INTERVAL_SEC,
        session_factory=AsyncSessionLocal,
        classifier=classifier,
        policy_engine=policy_engine,
    )
    if settings.INGESTION_ENABLED:
        await scheduler.start()
    try:
        yield
    finally:
        if scheduler.running:
            await scheduler.stop()


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    debug=settings.DEBUG,
    lifespan=lifespan,
)

if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin).rstrip("/") for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Authorization", "RefreshToken"],
    )

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}

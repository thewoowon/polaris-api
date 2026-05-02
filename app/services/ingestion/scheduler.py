"""Single-process async ingestion scheduler.

Lives inside the uvicorn event loop (lifespan start/stop). No Redis or
Celery — the review volume we're targeting is small. If/when multi-worker
or durable queues matter, swap to Arq/RQ/Celery behind the same
`IngestionScheduler.run_once` boundary.

Caveats:
- With uvicorn --workers N, each worker owns its own scheduler instance
  and would duplicate ingestion. Run the scheduler only in one worker
  (e.g. pin via INGESTION_ENABLED on a dedicated worker) for real deploys.
- When auto-pipeline is on, each new review commits in two stages: the
  review itself (always persisted) and then classification + policy in a
  separate transaction (rolls back if the LLM call errors, leaving the
  review intact for manual retry).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.classification import ClassificationResult
from app.models.policy import PolicyDecision
from app.models.review import Review
from app.services.audit.logger import AuditLogger
from app.services.classification.base import Classifier
from app.services.ingestion.base import ReviewSourceProto
from app.services.normalization import normalize_text
from app.services.policy.base import PolicyEngine


logger = logging.getLogger(__name__)


class IngestionScheduler:
    def __init__(
        self,
        *,
        sources: list[ReviewSourceProto],
        interval_sec: int,
        session_factory: async_sessionmaker[AsyncSession],
        classifier: Classifier | None = None,
        policy_engine: PolicyEngine | None = None,
    ):
        self.sources = sources
        self.interval_sec = interval_sec
        self.session_factory = session_factory
        self.classifier = classifier
        self.policy_engine = policy_engine

        self._task: asyncio.Task | None = None
        self._stop_event: asyncio.Event = asyncio.Event()

        self.started_at: datetime | None = None
        self.last_run_at: datetime | None = None
        self.last_stats: dict[str, Any] | None = None
        self.total_ingested: int = 0
        self.total_classified: int = 0
        self.error_count: int = 0

    # ─── public control ──────────────────────────────────────────────

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def auto_pipeline_enabled(self) -> bool:
        return self.classifier is not None and self.policy_engine is not None

    async def start(self) -> None:
        if self.running:
            return
        self._stop_event = asyncio.Event()
        self.started_at = datetime.now(timezone.utc)
        self._task = asyncio.create_task(self._loop(), name="ingestion-scheduler")
        logger.info(
            "ingestion scheduler started; sources=%s interval=%ds auto_pipeline=%s",
            [s.name for s in self.sources],
            self.interval_sec,
            self.auto_pipeline_enabled,
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=self.interval_sec + 5)
            except asyncio.TimeoutError:
                self._task.cancel()
                logger.warning("ingestion scheduler stop timed out; cancelling task")
        self._task = None
        logger.info("ingestion scheduler stopped")

    # ─── single run ──────────────────────────────────────────────────

    async def run_once(self) -> dict[str, Any]:
        """Fetch every source once + persist + optional auto-pipeline.

        Per-review commits isolate failures: a flaky classifier never
        loses a review, and a flaky source never poisons other sources'
        inserts.
        """
        ts = datetime.now(timezone.utc)
        per_source: dict[str, int] = {}
        total = 0
        classified = 0
        dedup_skipped = 0
        pipeline_errors: list[dict[str, str]] = []
        fetch_errors: list[dict[str, str]] = []

        async with self.session_factory() as db:
            for src in self.sources:
                try:
                    items = await src.fetch()
                except Exception as e:  # noqa: BLE001
                    logger.exception("source %s fetch failed: %s", src.name, e)
                    fetch_errors.append({"source": src.name, "error": str(e)})
                    self.error_count += 1
                    continue

                if items:
                    new_items, skipped = await self._filter_seen(db, items)
                    dedup_skipped += skipped
                else:
                    new_items = []

                created = 0
                for item in new_items:
                    review_id = await self._ingest_review(db, src.name, item)
                    if review_id is None:
                        continue
                    created += 1
                    total += 1

                    if self.auto_pipeline_enabled:
                        ok = await self._run_pipeline(db, review_id)
                        if ok:
                            classified += 1
                        else:
                            pipeline_errors.append(
                                {"review_id": str(review_id), "source": src.name}
                            )
                per_source[src.name] = created

        self.last_run_at = ts
        self.total_ingested += total
        self.total_classified += classified
        self.last_stats = {
            "ran_at": ts.isoformat(),
            "total": total,
            "classified": classified,
            "dedup_skipped": dedup_skipped,
            "per_source": per_source,
            "fetch_errors": fetch_errors,
            "pipeline_errors": pipeline_errors,
        }
        return self.last_stats

    async def _filter_seen(
        self, db: AsyncSession, items: list
    ) -> tuple[list, int]:
        """Dedup against existing (source, source_review_id) pairs.

        Items without a source_review_id pass through unchanged (synthetic
        UUID ids rarely collide; real sources always provide stable ids).
        Returns (kept_items, skipped_count).
        """
        # Group by source so we can do one query per source.
        per_source: dict = {}
        for item in items:
            sid = item.source_review_id
            if not sid:
                continue
            per_source.setdefault(item.source, set()).add(sid)

        seen: set[tuple] = set()
        for src_enum, ids in per_source.items():
            rows = await db.execute(
                select(Review.source, Review.source_review_id).where(
                    Review.source == src_enum,
                    Review.source_review_id.in_(list(ids)),
                )
            )
            for row in rows:
                seen.add((row[0], row[1]))

        kept: list = []
        skipped = 0
        for item in items:
            key = (item.source, item.source_review_id)
            if item.source_review_id and key in seen:
                skipped += 1
                continue
            kept.append(item)
        return kept, skipped

    async def _ingest_review(
        self,
        db: AsyncSession,
        src_name: str,
        item,
    ) -> int | None:
        """Commit a single review + its ingest audit row. Returns review id."""
        try:
            review = Review(
                source=item.source,
                source_review_id=item.source_review_id,
                app_version=item.app_version,
                os=item.os,
                locale=item.locale,
                rating=item.rating,
                author_name=item.author_name,
                raw_text=item.raw_text,
                normalized_text=normalize_text(item.raw_text),
                extra=item.extra,
            )
            db.add(review)
            await db.flush()
            audit = AuditLogger(db=db, actor="ingestion")
            await audit.record(
                entity_type="review",
                entity_id=review.id,
                action="ingest",
                after={
                    "source": item.source.value,
                    "source_review_id": item.source_review_id,
                    "via": src_name,
                },
            )
            await db.commit()
            return review.id
        except Exception as e:  # noqa: BLE001
            await db.rollback()
            logger.exception("ingest failed for source=%s: %s", src_name, e)
            self.error_count += 1
            return None

    async def _run_pipeline(self, db: AsyncSession, review_id: int) -> bool:
        """Run classifier + policy for a freshly-ingested review. Returns True on success."""
        assert self.classifier is not None and self.policy_engine is not None

        try:
            review = await db.get(Review, review_id)
            if review is None:
                return False

            audit = AuditLogger(db=db, actor="ingestion")

            cls_payload = await self.classifier.classify(
                review_text=review.normalized_text, review_id=review.id
            )
            cls_row = ClassificationResult(
                review_id=review.id,
                categories=[c.value for c in cls_payload.categories],
                sentiment=cls_payload.sentiment,
                urgency=cls_payload.urgency,
                confidence=cls_payload.confidence,
                entropy=cls_payload.entropy,
                ambiguity_score=cls_payload.ambiguity_score,
                top_candidates=(
                    [c.model_dump() for c in cls_payload.top_candidates]
                    if cls_payload.top_candidates
                    else None
                ),
                needs_clarification=cls_payload.needs_clarification,
                out_of_distribution=cls_payload.out_of_distribution,
                model_version=cls_payload.model_version,
            )
            db.add(cls_row)
            await db.flush()
            await audit.record(
                entity_type="classification_result",
                entity_id=cls_row.id,
                action="classify",
                after={
                    "categories": cls_row.categories,
                    "confidence": cls_row.confidence,
                    "ambiguity_score": cls_row.ambiguity_score,
                    "model_version": cls_row.model_version,
                    "via": "ingestion",
                },
            )

            policy_result = await self.policy_engine.evaluate(
                classification=cls_payload,
                rating=review.rating,
                app_version=review.app_version,
            )
            policy_row = PolicyDecision(
                review_id=review.id,
                action=policy_result.action,
                risk_score=policy_result.risk_score,
                reason_codes=policy_result.reason_codes,
                policy_version=policy_result.policy_version,
            )
            db.add(policy_row)
            await db.flush()
            await audit.record(
                entity_type="policy_decision",
                entity_id=policy_row.id,
                action="evaluate",
                after={
                    "action": policy_row.action.value,
                    "risk_score": policy_row.risk_score,
                    "reason_codes": policy_row.reason_codes,
                    "via": "ingestion",
                },
            )
            await db.commit()
            return True
        except Exception as e:  # noqa: BLE001
            await db.rollback()
            logger.exception("auto-pipeline failed for review_id=%s: %s", review_id, e)
            self.error_count += 1
            return False

    # ─── interval loop ───────────────────────────────────────────────

    async def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.run_once()
            except Exception as e:  # noqa: BLE001
                logger.exception("ingestion tick failed: %s", e)
                self.error_count += 1

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_sec)
            except asyncio.TimeoutError:
                pass

    # ─── status snapshot for API ─────────────────────────────────────

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "sources": [s.name for s in self.sources],
            "interval_sec": self.interval_sec,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_stats": self.last_stats,
            "total_ingested": self.total_ingested,
            "total_classified": self.total_classified,
            "error_count": self.error_count,
            "auto_pipeline": self.auto_pipeline_enabled,
            "auto_classifier": (
                self.classifier.model_version if self.classifier is not None else None
            ),
        }


# ─── module-level singleton ──────────────────────────────────────────

_scheduler: IngestionScheduler | None = None


def init_scheduler(
    *,
    sources: list[ReviewSourceProto],
    interval_sec: int,
    session_factory: async_sessionmaker[AsyncSession],
    classifier: Classifier | None = None,
    policy_engine: PolicyEngine | None = None,
) -> IngestionScheduler:
    global _scheduler
    _scheduler = IngestionScheduler(
        sources=sources,
        interval_sec=interval_sec,
        session_factory=session_factory,
        classifier=classifier,
        policy_engine=policy_engine,
    )
    return _scheduler


def get_scheduler() -> IngestionScheduler:
    if _scheduler is None:
        raise RuntimeError(
            "IngestionScheduler not initialised — did app.main's lifespan run?"
        )
    return _scheduler

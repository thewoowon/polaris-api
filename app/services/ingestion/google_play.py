"""Google Play review scraper via `google-play-scraper`.

Fetches the N newest reviews for a given package name. The upstream
library is sync, so we wrap the call in asyncio.to_thread to avoid
blocking the scheduler loop.

No API key needed — the library scrapes the public listing pages.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.models.review import ReviewSource
from app.services.ingestion.base import IngestionItem

logger = logging.getLogger(__name__)

try:
    from google_play_scraper import Sort, reviews as _gp_reviews

    _AVAILABLE = True
except ImportError:  # pragma: no cover — dep missing at runtime
    _AVAILABLE = False


class GooglePlaySource:
    name = "google_play"

    def __init__(
        self,
        *,
        app_id: str,
        lang: str = "ko",
        country: str = "kr",
        count: int = 20,
    ):
        self.app_id = app_id
        self.lang = lang
        self.country = country
        self.count = max(1, min(count, 100))

    async def fetch(self) -> list[IngestionItem]:
        if not _AVAILABLE:
            logger.warning("google-play-scraper not installed; skipping google_play")
            return []
        if not self.app_id:
            return []

        try:
            result, _continuation = await asyncio.to_thread(
                _gp_reviews,
                self.app_id,
                lang=self.lang,
                country=self.country,
                sort=Sort.NEWEST,
                count=self.count,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("google_play %s fetch failed: %s", self.app_id, e)
            raise

        items: list[IngestionItem] = []
        for r in result or []:
            text = (r.get("content") or "").strip()
            if not text:
                continue
            score = r.get("score")
            items.append(
                IngestionItem(
                    source=ReviewSource.GOOGLE_PLAY,
                    source_review_id=str(r.get("reviewId")) if r.get("reviewId") else None,
                    app_version=r.get("reviewCreatedVersion"),
                    os="android",
                    locale=f"{self.lang}-{self.country.upper()}",
                    rating=int(score) if isinstance(score, (int, float)) and 1 <= score <= 5 else None,
                    author_name=r.get("userName"),
                    raw_text=text,
                    extra={
                        "gp_app_id": self.app_id,
                        "gp_at": _to_iso(r.get("at")),
                        "gp_thumbs_up": r.get("thumbsUpCount"),
                        "gp_reply": ((r.get("replyContent") or None) is not None),
                    },
                )
            )
        return items


def _to_iso(v: Any) -> str | None:
    if v is None:
        return None
    try:
        return v.isoformat()
    except AttributeError:
        return str(v)

"""App Store review scraper via the public RSS feed.

Apple exposes a JSON variant of the RSS at:
  https://itunes.apple.com/{country}/rss/customerreviews/page=1/id={app_id}/sortby=mostrecent/json

First entry in the feed is sometimes app metadata (no `im:rating`); we
skip entries missing a rating. Max ~50 reviews per page × 10 pages; for
MVP we grab page 1 only.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.models.review import ReviewSource
from app.services.ingestion.base import IngestionItem

logger = logging.getLogger(__name__)


RSS_URL = (
    "https://itunes.apple.com/{country}/rss/customerreviews"
    "/page=1/id={app_id}/sortby=mostrecent/json"
)


class AppStoreSource:
    name = "app_store"

    def __init__(self, *, app_id: str, country: str = "kr"):
        self.app_id = app_id
        self.country = country

    async def fetch(self) -> list[IngestionItem]:
        if not self.app_id:
            return []

        url = RSS_URL.format(country=self.country, app_id=self.app_id)
        try:
            async with httpx.AsyncClient(timeout=10.0) as http:
                res = await http.get(url, headers={"user-agent": "polaris-voc/0.1"})
        except httpx.HTTPError as e:
            logger.warning("app_store HTTP error for %s: %s", url, e)
            raise

        if res.status_code != 200:
            logger.warning("app_store RSS %s returned %s", url, res.status_code)
            return []

        try:
            data = res.json()
        except Exception as e:  # noqa: BLE001
            logger.warning("app_store RSS non-JSON body: %s", e)
            return []

        entries = (data.get("feed") or {}).get("entry") or []
        if isinstance(entries, dict):  # single-entry feeds come back as a dict
            entries = [entries]

        items: list[IngestionItem] = []
        for e in entries:
            rating = _label(e, "im:rating")
            if rating is None:
                continue  # likely the app metadata entry
            rid = _label(e, "id")
            # id value is a full URL ending with the numeric review id
            review_id = rid.rsplit("/", 1)[-1] if rid else None
            title = _label(e, "title") or ""
            content = _label(e, "content") or ""
            text = f"{title}\n\n{content}".strip() if title and content else (title or content).strip()
            if not text:
                continue
            author = None
            author_obj = e.get("author") or {}
            if isinstance(author_obj, dict):
                name_obj = author_obj.get("name") or {}
                if isinstance(name_obj, dict):
                    author = name_obj.get("label")
            try:
                rating_int = int(rating)
            except (TypeError, ValueError):
                rating_int = None
            items.append(
                IngestionItem(
                    source=ReviewSource.APP_STORE,
                    source_review_id=review_id,
                    app_version=_label(e, "im:version"),
                    os="ios",
                    locale=self.country,
                    rating=rating_int if rating_int and 1 <= rating_int <= 5 else None,
                    author_name=author,
                    raw_text=text,
                    extra={
                        "as_app_id": self.app_id,
                        "as_country": self.country,
                        "as_updated": _label(e, "updated"),
                        "as_vote_count": _label(e, "im:voteCount"),
                    },
                )
            )
        return items


def _label(entry: dict[str, Any], key: str) -> str | None:
    val = entry.get(key)
    if isinstance(val, dict):
        label = val.get("label")
        return str(label) if label is not None else None
    return None

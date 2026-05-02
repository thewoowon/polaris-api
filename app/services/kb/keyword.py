"""Keyword search with weighted scoring over title / tags / body.

Blueprint §12.3 positioning: SQL LIKE / BM25 before embeddings. We're
BM25-ish (hand-rolled) — a full BM25 needs idf precomputation and
per-term df, not worth it while the KB is ~dozens of docs. The scorer
weights tag hits highest, then title, then body; snippets are drawn
around the first matching term for each hit.

Moving to Postgres full-text search (`to_tsvector` + `plainto_tsquery`)
or pgvector is a drop-in swap behind the same `search()` contract.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kb import DocType, KbDocument
from app.schemas.kb import KbSearchHit


# Split on whitespace + common punctuation. Korean text uses spaces between
# morphemes in most reviews, so this is good enough without a real tokenizer.
_TOKEN_SPLIT = re.compile(r"[\s,.!?:;/\\(){}\[\]\"'<>~`@#$%^&*+=|·…ㅡ\-—_]+")

# Drop very short tokens (Korean particles / English stopwords) to keep the
# signal clean. Real stopword list lands with the proper FTS migration.
_MIN_TOKEN_LEN = 2


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    parts = _TOKEN_SPLIT.split(text.lower())
    return [p for p in parts if len(p) >= _MIN_TOKEN_LEN]


@dataclass
class _Scored:
    doc: KbDocument
    score: float
    first_hit_idx: int  # -1 if matched only on tags


class KeywordKnowledgeBase:
    """Keyword matcher with (tag, title, body) weighting."""

    # Tuned on 14-doc seed; bump tag weight further if we see tag-only hits
    # losing to body noise.
    TAG_WEIGHT = 5.0
    TITLE_WEIGHT = 3.0
    BODY_WEIGHT = 1.0

    # Long docs get a mild length penalty so short, precise FAQ answers win
    # over huge incident-response essays that happen to contain the term.
    LENGTH_NORM_CHARS = 2000

    async def search(
        self,
        *,
        db: AsyncSession,
        query: str,
        top_k: int = 5,
        doc_types: list[DocType] | None = None,
    ) -> list[KbSearchHit]:
        terms = _tokenize(query)
        if not terms:
            return []

        # Fetch all active docs once. For ~hundreds of docs this is fast
        # and lets tag-only matches (where neither title nor body contain
        # the term) still surface.
        stmt = select(KbDocument).where(KbDocument.active.is_(True))
        if doc_types:
            stmt = stmt.where(KbDocument.doc_type.in_(doc_types))
        rows = (await db.execute(stmt)).scalars().all()

        scored: list[_Scored] = []
        for doc in rows:
            s = self._score_doc(doc, terms)
            if s.score > 0:
                scored.append(s)

        scored.sort(key=lambda x: x.score, reverse=True)

        hits: list[KbSearchHit] = []
        for entry in scored[:top_k]:
            doc = entry.doc
            snippet = self._make_snippet(doc.content, terms, entry.first_hit_idx)
            hits.append(
                KbSearchHit(
                    document_id=doc.id,
                    chunk_id=None,
                    title=doc.title,
                    doc_type=doc.doc_type,
                    score=round(entry.score, 3),
                    snippet=snippet,
                )
            )
        return hits

    # ─── internals ──────────────────────────────────────────────────

    def _score_doc(self, doc: KbDocument, terms: list[str]) -> _Scored:
        title_l = doc.title.lower()
        content_l = doc.content.lower()
        tags_l = [t.lower() for t in (doc.tags or [])]

        score = 0.0
        first_hit = -1

        for term in terms:
            # Tag match: any tag equals or substring-contains the term.
            tag_hit = any(term == tag or term in tag for tag in tags_l)
            if tag_hit:
                score += self.TAG_WEIGHT

            title_hits = title_l.count(term)
            if title_hits:
                score += title_hits * self.TITLE_WEIGHT
                if first_hit < 0:
                    first_hit = title_l.find(term) + len(doc.title) - len(title_l)
                    # Fall through — body hit location is better for snippets.

            body_hits = content_l.count(term)
            if body_hits:
                score += body_hits * self.BODY_WEIGHT
                body_idx = content_l.find(term)
                if body_idx >= 0 and (first_hit < 0 or body_idx < first_hit):
                    first_hit = body_idx

        if score > 0:
            # Light length penalty: halves the score of a 2000-char doc
            # relative to a tiny one with the same raw hits.
            penalty = 1.0 + len(doc.content) / self.LENGTH_NORM_CHARS
            score = score / penalty

        return _Scored(doc=doc, score=score, first_hit_idx=first_hit)

    def _make_snippet(self, content: str, terms: list[str], hint_idx: int) -> str:
        if hint_idx < 0 or hint_idx >= len(content):
            # Tag-only match: return the head of the doc.
            return content[:120].rstrip()
        start = max(0, hint_idx - 40)
        end = min(len(content), hint_idx + 80)
        prefix = "…" if start > 0 else ""
        suffix = "…" if end < len(content) else ""
        return prefix + content[start:end].strip() + suffix

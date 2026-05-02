from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kb import DocType
from app.schemas.kb import KbSearchHit


class KnowledgeBase(Protocol):
    """KB retrieval contract. Phase-1 impl is keyword; Phase-3 adds pgvector."""

    async def search(
        self,
        *,
        db: AsyncSession,
        query: str,
        top_k: int = 5,
        doc_types: list[DocType] | None = None,
    ) -> list[KbSearchHit]: ...

"""Synthetic source — emits 0-2 fake reviews per tick.

Useful for demos + verifying the scheduler plumbing without hitting real
store APIs. Content is randomised across the same buckets scripts/seed.py
uses, so the emitted stream has the same category mix as the baseline
dataset.
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone

from app.models.review import ReviewSource
from app.services.ingestion.base import IngestionItem


_TEMPLATES: list[tuple[str, tuple[int, int]]] = [
    ("업데이트 후 앱이 자꾸 튕깁니다. 계속 로딩만 되고 사용이 불가해요.", (1, 2)),
    ("결제했는데 구독이 적용 안 됐어요. 환불 부탁드립니다.", (1, 2)),
    ("구글 로그인이 계속 실패합니다. 계정 잠김 같아요.", (1, 2)),
    ("업데이트 후 앱이 너무 느려졌어요. 리스트 스크롤이 렉 걸립니다.", (1, 3)),
    ("다크모드에서 버튼이 잘 안 보입니다. 색 대비가 약해요.", (2, 4)),
    ("위젯이 있으면 좋겠어요. 홈 화면에서 바로 확인하고 싶습니다.", (3, 4)),
    ("정말 잘 쓰고 있어요. 유용합니다. 감사합니다.", (4, 5)),
    ("업데이트되고 훨씬 좋아졌어요!", (4, 5)),
    ("고객센터 답이 너무 늦어요.", (1, 3)),
    ("개인정보 처리방침 어디서 확인하나요?", (3, 4)),
]


_SOURCES = [ReviewSource.GOOGLE_PLAY, ReviewSource.APP_STORE, ReviewSource.INTERNAL]
_APP_VERSIONS = ["3.2.1", "3.3.0", "3.3.1", "3.4.0"]
_LOCALES = ["ko-KR", "ko-KR", "ko-KR", "en-US"]
_OSES = ["android", "ios", "web"]
_AUTHORS = ["익명", "user_a", "user_b", "user_c", None]


class SyntheticSource:
    name = "synthetic"

    def __init__(self, *, rng: random.Random | None = None):
        # Don't seed → emit fresh variety across process restarts.
        self._rng = rng or random.Random()

    async def fetch(self) -> list[IngestionItem]:
        n = self._rng.randint(0, 2)
        items: list[IngestionItem] = []
        for _ in range(n):
            text, rating_range = self._rng.choice(_TEMPLATES)
            items.append(
                IngestionItem(
                    source=self._rng.choice(_SOURCES),
                    # UUID keeps (source, source_review_id) uniq even under
                    # multi-worker deployments.
                    source_review_id=f"synth-{uuid.uuid4().hex[:12]}",
                    app_version=self._rng.choice(_APP_VERSIONS),
                    os=self._rng.choice(_OSES),
                    locale=self._rng.choice(_LOCALES),
                    rating=self._rng.randint(*rating_range),
                    author_name=self._rng.choice(_AUTHORS),
                    raw_text=text,
                    extra={
                        "synthetic": True,
                        "minted_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
            )
        return items

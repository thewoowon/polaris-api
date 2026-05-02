from app.models.classification import ReviewCategory, Sentiment, Urgency
from app.schemas.classification import ClassificationPayload, TopCandidate
from app.services.classification.scoring import compute_from_candidates


_BUG_KEYWORDS = ("crash", "bug", "에러", "버그", "튕", "오류")
_PAYMENT_KEYWORDS = ("결제", "환불", "payment", "refund", "charge")
_LOGIN_KEYWORDS = ("login", "로그인", "계정", "sign in", "signup")
_PERF_KEYWORDS = ("느림", "느려", "렉", "lag", "slow", "freeze")
_PRAISE_KEYWORDS = ("good", "great", "love", "최고", "좋아요", "감사")


class StubClassifier:
    """Deterministic heuristic classifier for local dev / CI / frontend integration.

    Swapped out for the LLM-backed classifier in app.services.classification.llm
    once that lands. Keeps the same async contract so routes don't change.
    """

    model_version = "stub-v0"

    async def classify(
        self, *, review_text: str, review_id: int | None = None
    ) -> ClassificationPayload:
        t = review_text.lower()

        categories: list[ReviewCategory] = []
        if any(k in t for k in _BUG_KEYWORDS):
            categories.append(ReviewCategory.BUG)
        if any(k in t for k in _PAYMENT_KEYWORDS):
            categories.extend([ReviewCategory.PAYMENT, ReviewCategory.REFUND])
        if any(k in t for k in _LOGIN_KEYWORDS):
            categories.append(ReviewCategory.LOGIN_ACCOUNT)
        if any(k in t for k in _PERF_KEYWORDS):
            categories.append(ReviewCategory.PERFORMANCE)
        if any(k in t for k in _PRAISE_KEYWORDS):
            categories.append(ReviewCategory.PRAISE)
        if not categories:
            categories.append(ReviewCategory.OTHER)

        categories = list(dict.fromkeys(categories))  # dedupe, preserve order

        if ReviewCategory.PRAISE in categories and len(categories) == 1:
            sentiment = Sentiment.POSITIVE
            urgency = Urgency.LOW
            confidence = 0.78
        elif any(
            c in categories
            for c in (
                ReviewCategory.BUG,
                ReviewCategory.PAYMENT,
                ReviewCategory.REFUND,
                ReviewCategory.LOGIN_ACCOUNT,
            )
        ):
            sentiment = Sentiment.NEGATIVE
            urgency = Urgency.HIGH
            confidence = 0.62
        else:
            sentiment = Sentiment.NEUTRAL
            urgency = Urgency.LOW
            confidence = 0.4

        # Build top-3 candidate distribution. Primary = confidence; runners-up
        # decay so there's some signal for margin/entropy.
        decay_step = 0.12
        top_candidates = [
            TopCandidate(
                label=c.value,
                score=round(max(0.05, confidence - i * decay_step), 4),
            )
            for i, c in enumerate(categories[:3])
        ]
        # Pad to 3 with low-score "other" so ties on 1-category don't short-circuit entropy.
        while len(top_candidates) < 3:
            filler = 0.05 + 0.01 * len(top_candidates)
            top_candidates.append(TopCandidate(label="other", score=round(filler, 4)))

        cand_dicts = [c.model_dump() for c in top_candidates]
        entropy_norm, ambiguity = compute_from_candidates(
            top1_confidence=confidence,
            top_candidates=cand_dicts,
            is_ood=False,
        )

        return ClassificationPayload(
            categories=categories,
            sentiment=sentiment,
            urgency=urgency,
            confidence=confidence,
            entropy=round(entropy_norm, 4),
            ambiguity_score=round(ambiguity, 4),
            top_candidates=top_candidates,
            needs_clarification=confidence < 0.5,
            out_of_distribution=False,
            model_version=self.model_version,
        )

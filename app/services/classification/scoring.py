"""Pure functions for confidence / ambiguity scoring (blueprint §10).

Kept as a standalone module so tests can hit it without spinning the app,
and so the formula + weights live in one place. Policy engine and the
classifiers both call into here.
"""

from __future__ import annotations

import math
from typing import Iterable


# Default weights for the composite ambiguity score. They sum to 1.0 so the
# output stays in [0, 1]. Tune after we see real distributions — do NOT
# scatter magic numbers elsewhere.
DEFAULT_WEIGHTS: tuple[float, float, float, float] = (0.30, 0.20, 0.30, 0.20)

# A review is "very ambiguous" once the composite score crosses this.
# Policy engine treats the Venn intersection of (mid confidence, high
# ambiguity) as a clarification candidate.
HIGH_AMBIGUITY: float = 0.65


def shannon_entropy(scores: Iterable[float]) -> float:
    """Treat `scores` as a distribution, re-normalise if needed, return H (bits)."""
    vals = [s for s in scores if s > 0]
    total = sum(vals)
    if total <= 0 or len(vals) <= 1:
        return 0.0
    probs = [v / total for v in vals]
    return -sum(p * math.log2(p) for p in probs if p > 0)


def normalized_entropy(scores: Iterable[float]) -> float:
    """Shannon entropy divided by log2(n) so it lives in [0, 1]."""
    vals = [s for s in scores if s > 0]
    if len(vals) <= 1:
        return 0.0
    max_h = math.log2(len(vals))
    if max_h <= 0:
        return 0.0
    return shannon_entropy(vals) / max_h


def low_margin(top1: float, top2: float) -> float:
    """1.0 when top1 ≈ top2 (tied → ambiguous); 0.0 when gap is >= 1.0 (confident)."""
    gap = max(0.0, min(1.0, top1 - top2))
    return 1.0 - gap


def ambiguity_score(
    *,
    top1_confidence: float,
    entropy_norm: float,
    is_ood: bool,
    top1_score: float | None = None,
    top2_score: float | None = None,
    weights: tuple[float, float, float, float] = DEFAULT_WEIGHTS,
) -> float:
    """Blueprint §10.1 composite:
        a*(1 - top1_conf) + b*entropy_norm + c*is_ood + d*low_margin(top1, top2)

    All four components are already in [0, 1]; weights sum to 1.0, so the
    output is clamped to [0, 1] defensively but should fall there naturally.
    """
    a, b, c, d = weights
    conf_deficit = max(0.0, 1.0 - top1_confidence)
    ood_term = 1.0 if is_ood else 0.0
    margin_term = (
        low_margin(top1_score, top2_score)
        if top1_score is not None and top2_score is not None
        else 0.0
    )
    raw = a * conf_deficit + b * entropy_norm + c * ood_term + d * margin_term
    return max(0.0, min(1.0, raw))


def compute_from_candidates(
    *,
    top1_confidence: float,
    top_candidates: list[dict] | None,
    is_ood: bool,
) -> tuple[float, float]:
    """Convenience wrapper: returns (entropy_norm, ambiguity_score).

    `top_candidates` is the wire-format list of {label, score} dicts.
    """
    if not top_candidates:
        return 0.0, ambiguity_score(
            top1_confidence=top1_confidence,
            entropy_norm=0.0,
            is_ood=is_ood,
        )

    scores = [float(c.get("score", 0.0)) for c in top_candidates]
    entropy_norm = normalized_entropy(scores)
    top1 = scores[0] if scores else None
    top2 = scores[1] if len(scores) > 1 else None
    return entropy_norm, ambiguity_score(
        top1_confidence=top1_confidence,
        entropy_norm=entropy_norm,
        is_ood=is_ood,
        top1_score=top1,
        top2_score=top2,
    )

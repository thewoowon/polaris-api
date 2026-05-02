"""YAML-driven policy rules evaluator.

Rules live in `rules.yaml` (co-located). The file is loaded once at engine
instantiation. A rule is a tuple of (when predicate, then action + risk +
reasons); the evaluator walks the rule list top-to-bottom and returns the
first match.

Blueprint §24 — "정책 룰은 코드 외부화 가능하게" — so non-engineers can
tweak thresholds without a deploy.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.models.classification import ReviewCategory, Sentiment
from app.models.policy import PolicyAction
from app.schemas.classification import ClassificationPayload
from app.schemas.policy import PolicyEvaluateResult


RULES_PATH = Path(__file__).parent / "rules.yaml"


class PolicyRulesError(RuntimeError):
    """Raised when rules.yaml is missing, malformed, or has no matching rule."""


@dataclass
class _Ctx:
    categories: list[ReviewCategory]
    sentiment: Sentiment
    confidence: float
    rating: int | None
    out_of_distribution: bool
    ambiguity_score: float
    needs_clarification: bool


# ─── predicate evaluator ────────────────────────────────────────────────

def _match(ctx: _Ctx, pred: Any) -> bool:
    # `when: always` shorthand
    if pred == "always":
        return True

    if not isinstance(pred, dict):
        raise PolicyRulesError(f"predicate must be a mapping or 'always': {pred!r}")
    if len(pred) != 1:
        raise PolicyRulesError(
            f"predicate mapping must have exactly one key (wrap in all_of/any_of): {pred!r}"
        )
    (key, value), = pred.items()

    if key == "all_of":
        if not isinstance(value, list):
            raise PolicyRulesError("all_of requires a list")
        return all(_match(ctx, p) for p in value)
    if key == "any_of":
        if not isinstance(value, list):
            raise PolicyRulesError("any_of requires a list")
        return any(_match(ctx, p) for p in value)
    if key == "not":
        return not _match(ctx, value)

    if key == "category_in":
        wanted = {str(c) for c in value}
        return any(c.value in wanted for c in ctx.categories)
    if key == "categories_exact":
        wanted = {str(c) for c in value}
        actual = {c.value for c in ctx.categories}
        return actual == wanted
    if key == "sentiment":
        return ctx.sentiment.value == str(value)
    if key == "out_of_distribution":
        return ctx.out_of_distribution is bool(value)
    if key == "needs_clarification":
        return ctx.needs_clarification is bool(value)
    if key == "confidence_below":
        return ctx.confidence < float(value)
    if key == "confidence_at_least":
        return ctx.confidence >= float(value)
    if key == "ambiguity_at_least":
        return ctx.ambiguity_score >= float(value)
    if key == "rating_at_most":
        return ctx.rating is not None and ctx.rating <= int(value)
    if key == "rating_at_least":
        return ctx.rating is not None and ctx.rating >= int(value)
    if key == "always":
        return bool(value)

    raise PolicyRulesError(f"unknown predicate: {key!r}")


# ─── rule document loader ───────────────────────────────────────────────

def load_rules_doc(path: Path = RULES_PATH) -> dict:
    if not path.exists():
        raise PolicyRulesError(f"rules file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as f:
            doc = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise PolicyRulesError(f"rules file parse error: {e}") from e

    if not isinstance(doc, dict) or "rules" not in doc:
        raise PolicyRulesError("rules file must be a mapping with a top-level `rules:` list")
    if not isinstance(doc["rules"], list) or not doc["rules"]:
        raise PolicyRulesError("`rules` must be a non-empty list")

    # Validate each rule has required keys + an action that maps to a real enum.
    for i, rule in enumerate(doc["rules"]):
        if not isinstance(rule, dict):
            raise PolicyRulesError(f"rule #{i} must be a mapping")
        for required in ("id", "action", "risk", "when"):
            if required not in rule:
                raise PolicyRulesError(f"rule #{i} missing `{required}`")
        try:
            PolicyAction(rule["action"])
        except ValueError as e:
            raise PolicyRulesError(f"rule {rule.get('id')}: invalid action {rule['action']!r}") from e
    return doc


# ─── evaluator class ────────────────────────────────────────────────────

class YamlPolicyEngine:
    def __init__(self, *, path: Path = RULES_PATH):
        self._path = path
        self._doc = load_rules_doc(path)
        self.policy_version: str = str(self._doc.get("version") or "rules-v1")

    @property
    def rules_doc(self) -> dict:
        return self._doc

    @property
    def rules_path(self) -> Path:
        return self._path

    def reload(self) -> None:
        """Re-read rules.yaml from disk. Atomic — on parse failure the old
        ruleset is kept and the caller's exception surfaces."""
        new_doc = load_rules_doc(self._path)
        self._doc = new_doc
        self.policy_version = str(new_doc.get("version") or "rules-v1")

    async def evaluate(
        self,
        *,
        classification: ClassificationPayload,
        rating: int | None = None,
        app_version: str | None = None,  # reserved for future rules
    ) -> PolicyEvaluateResult:
        ctx = _Ctx(
            categories=list(classification.categories),
            sentiment=classification.sentiment,
            confidence=classification.confidence,
            rating=rating,
            out_of_distribution=classification.out_of_distribution,
            ambiguity_score=classification.ambiguity_score or 0.0,
            needs_clarification=classification.needs_clarification,
        )

        for rule in self._doc["rules"]:
            if _match(ctx, rule["when"]):
                reasons = list(rule.get("reasons") or [])
                return PolicyEvaluateResult(
                    action=PolicyAction(rule["action"]),
                    risk_score=float(rule["risk"]),
                    reason_codes=reasons,
                    policy_version=self.policy_version,
                )

        raise PolicyRulesError(
            "no rule matched — add a `when: always` catch-all at the bottom of rules.yaml"
        )

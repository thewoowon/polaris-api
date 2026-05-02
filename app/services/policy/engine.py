"""Default policy engine — thin re-export over the YAML-driven evaluator.

Kept separate so callers (registry, seed script, tests) depend on a stable
class name while the actual rule evaluation logic lives in yaml_engine.py.
"""

from app.services.policy.yaml_engine import YamlPolicyEngine


class RuleBasedPolicyEngine(YamlPolicyEngine):
    """Polaris default policy engine backed by `rules.yaml`.

    Blueprint §24 — rules externalised so non-engineers can edit thresholds
    without a deploy. Hot-reload is NOT supported; restart uvicorn after
    editing rules.yaml.
    """

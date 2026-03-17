# agent_platform/model_router/policy.py
from __future__ import annotations
from agent_platform.model_router.catalog import ModelCatalog

COMPLEXITY_MAX_TIER: dict[str, int] = {
    "small": 3,
    "medium": 2,
    "large": 1,
}


class RoutingPolicy:
    def __init__(
        self,
        stage_models: dict,
        catalog: ModelCatalog,
        default_model: str = "gpt-5.4",
    ) -> None:
        self._stage_models = stage_models
        self._catalog = catalog
        self._default = default_model

    def resolve(self, stage: str, complexity: str, executor: str = "") -> str:
        _MISSING = object()
        stage_cfg = self._stage_models.get(stage, _MISSING)

        if stage_cfg is not _MISSING:
            # Stage is explicitly configured — only use stage-level resolution.
            # 1. exact stage+complexity match
            if complexity in stage_cfg:
                return stage_cfg[complexity]

            # 2. stage default
            if "default" in stage_cfg:
                return stage_cfg["default"]

            # 3. final fallback (stage present but no matching key)
            return self._default

        # Stage not configured at all → tier-based via catalog
        # COMPLEXITY_MAX_TIER maps complexity → the exact tier we want:
        #   small→3 (lightest), medium→2, large→1 (strongest).
        # We find candidates with tier <= max_tier, then pick the one whose
        # tier is closest to max_tier (cheapest sufficient model).
        if executor:
            max_tier = COMPLEXITY_MAX_TIER.get(complexity, 2)
            candidates = [
                e for e in self._catalog.for_executor(executor)
                if e.tier <= max_tier
            ]
            if candidates:
                # candidates are sorted ascending by tier; last = highest tier
                # = lightest model that satisfies the complexity constraint
                return candidates[-1].name

        # 4. final fallback
        return self._default

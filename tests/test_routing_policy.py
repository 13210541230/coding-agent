from __future__ import annotations
from agent_platform.model_router.catalog import ModelCatalog, ModelEntry
from agent_platform.model_router.policy import RoutingPolicy

CATALOG = ModelCatalog([
    ModelEntry("strong", "codex", tier=1, context_window=100, tags=()),
    ModelEntry("medium", "codex", tier=2, context_window=100, tags=()),
    ModelEntry("light",  "codex", tier=3, context_window=100, tags=()),
])

STAGE_MODELS = {
    "analysis": {"small": "medium", "large": "strong"},
    "planning":  {"default": "strong"},
    "review":    {},
}

def policy():
    return RoutingPolicy(STAGE_MODELS, CATALOG, default_model="strong")

def test_exact_stage_complexity_match():
    assert policy().resolve("analysis", "small", "codex") == "medium"

def test_exact_stage_complexity_large():
    assert policy().resolve("analysis", "large", "codex") == "strong"

def test_stage_default_when_no_complexity_match():
    assert policy().resolve("planning", "small", "codex") == "strong"

def test_final_fallback_when_no_config():
    assert policy().resolve("review", "medium", "codex") == "strong"

def test_tier_based_when_no_name_configured():
    # stage not in stage_models → tier-based → large→tier1 → "strong"
    assert policy().resolve("execution_loop", "large", "codex") == "strong"

def test_tier_based_small_uses_tier3():
    assert policy().resolve("execution_loop", "small", "codex") == "light"

def test_unknown_executor_falls_back_to_default():
    assert policy().resolve("execution_loop", "large", "unknown_executor") == "strong"

def test_no_executor_unconfigured_stage_falls_back_to_default():
    assert policy().resolve("execution_loop", "large") == "strong"

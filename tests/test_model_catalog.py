# tests/test_model_catalog.py
from __future__ import annotations
from agent_platform.model_router.catalog import ModelEntry, ModelCatalog

SAMPLE = [
    ModelEntry("opus",   "claude_code", tier=1, context_window=1000000, tags=("reasoning",)),
    ModelEntry("sonnet", "claude_code", tier=2, context_window=1000000, tags=("balanced",)),
    ModelEntry("haiku",  "claude_code", tier=3, context_window=200000,  tags=("fast",)),
    ModelEntry("gpt-5.4","codex",       tier=1, context_window=1050000, tags=("reasoning",)),
    ModelEntry("mini",   "codex",       tier=3, context_window=400000,  tags=("fast",)),
]

def catalog():
    return ModelCatalog(SAMPLE)

def test_for_executor_returns_sorted_by_tier():
    entries = catalog().for_executor("claude_code")
    assert [e.name for e in entries] == ["opus", "sonnet", "haiku"]

def test_for_executor_unknown_returns_empty():
    assert catalog().for_executor("unknown") == []

def test_best_for_returns_lowest_tier_within_max():
    assert catalog().best_for("claude_code", max_tier=2).name == "opus"

def test_best_for_max_tier_3():
    assert catalog().best_for("codex", max_tier=3).name == "gpt-5.4"

def test_best_for_no_match_returns_none():
    assert catalog().best_for("claude_code", max_tier=0) is None

def test_by_tier_cross_executor():
    tier1 = catalog().by_tier(1)
    names = {e.name for e in tier1}
    assert names == {"opus", "gpt-5.4"}

def test_user_entry_overrides_builtin_by_name_and_executor():
    override = ModelEntry("opus", "claude_code", tier=2, context_window=99, tags=("custom",))
    c = ModelCatalog(SAMPLE + [override])
    entries = c.for_executor("claude_code")
    assert len(c.for_executor("claude_code")) == 3
    opus = next(e for e in entries if e.name == "opus")
    assert opus.context_window == 99


def test_default_catalog_has_all_executors():
    from agent_platform.model_router.default_catalog import DEFAULT_CATALOG
    from agent_platform.model_router.catalog import ModelCatalog
    c = ModelCatalog(DEFAULT_CATALOG)
    for executor in ("claude_code", "codex", "mycodex"):
        assert len(c.for_executor(executor)) > 0, f"no models for {executor}"
    # tier-1 exists for each executor
    for executor in ("claude_code", "codex", "mycodex"):
        assert c.best_for(executor, max_tier=1) is not None

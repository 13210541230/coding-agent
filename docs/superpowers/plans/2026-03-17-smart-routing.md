# Smart Routing Layer Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace stub ModelRouter/AgentRuntime with a real routing layer that selects CLI executor and model per task complexity, with automatic fallback when executors are unavailable.

**Architecture:** Three new modules (catalog, policy, smart_router) handle model selection; two new modules (registry, fallback) handle executor dispatch with priority-queue fallback. Existing public interfaces (ModelRouter.model_for, ExecutorRouterV2.choose_executor) are preserved via delegation. Orchestrator wires everything at init.

**Tech Stack:** Python 3.10+, dataclasses, subprocess (existing), pytest. No new dependencies.

---

## File Structure

### New Files
```
agent_platform/model_router/catalog.py         ModelEntry dataclass + ModelCatalog class
agent_platform/model_router/default_catalog.py DEFAULT_CATALOG list (all built-in models)
agent_platform/model_router/policy.py          RoutingPolicy (stage+complexity → model name)
agent_platform/model_router/smart_router.py    AssessResult dataclass + SmartRouter class
agent_platform/executor_layer/registry.py      ExecutorEntry dataclass + ExecutorRegistry class
agent_platform/executor_layer/fallback.py      ExecutorUnavailableError + FallbackChain class
tests/test_model_catalog.py
tests/test_routing_policy.py
tests/test_smart_router.py
tests/test_executor_registry.py
tests/test_fallback_chain.py
```

### Modified Files
```
agent_platform/model_router/__init__.py        export new symbols
agent_platform/executor_layer/__init__.py      export new symbols
agent_platform/agent_runtime/runtime.py        accept SmartRouter+RoutingPolicy, keep old path
agent_platform/model_router/router.py          delegate to RoutingPolicy internally
agent_platform/orchestrator/system.py          wire new modules; handle ExecutorUnavailableError
agent_platform/cli.py                          add disable-executor / enable-executor subcommands
tests/test_cli.py                              add tests for new CLI subcommands
tests/test_routing_and_models.py               update gpt-5.4 assertion to match new default
```

---

## Task 1: ModelEntry + ModelCatalog

**Files:**
- Create: `agent_platform/model_router/catalog.py`
- Create: `tests/test_model_catalog.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_model_catalog.py
from __future__ import annotations
import pytest
from agent_platform.model_router.catalog import ModelEntry, ModelCatalog

SAMPLE = [
    ModelEntry("opus",   "claude_code", tier=1, context_window=1000000, tags=["reasoning"]),
    ModelEntry("sonnet", "claude_code", tier=2, context_window=1000000, tags=["balanced"]),
    ModelEntry("haiku",  "claude_code", tier=3, context_window=200000,  tags=["fast"]),
    ModelEntry("gpt-5.4","codex",       tier=1, context_window=1050000, tags=["reasoning"]),
    ModelEntry("mini",   "codex",       tier=3, context_window=400000,  tags=["fast"]),
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
    override = ModelEntry("opus", "claude_code", tier=2, context_window=99, tags=["custom"])
    c = ModelCatalog(SAMPLE + [override])
    entries = c.for_executor("claude_code")
    opus = next(e for e in entries if e.name == "opus")
    assert opus.context_window == 99
```

- [ ] **Step 2: Run tests — verify they fail**

```
pytest tests/test_model_catalog.py -v
```
Expected: `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Implement catalog.py**

```python
# agent_platform/model_router/catalog.py
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class ModelEntry:
    name: str
    executor: str
    tier: int
    context_window: int
    tags: list[str] = field(default_factory=list)


class ModelCatalog:
    def __init__(self, entries: list[ModelEntry]) -> None:
        # user entries override built-ins with same (name, executor)
        seen: dict[tuple[str, str], ModelEntry] = {}
        for e in entries:
            seen[(e.name, e.executor)] = e
        self._entries = list(seen.values())

    def for_executor(self, executor: str) -> list[ModelEntry]:
        return sorted(
            [e for e in self._entries if e.executor == executor],
            key=lambda e: e.tier,
        )

    def best_for(self, executor: str, max_tier: int = 4) -> ModelEntry | None:
        candidates = [e for e in self.for_executor(executor) if e.tier <= max_tier]
        return candidates[0] if candidates else None

    def by_tier(self, tier: int) -> list[ModelEntry]:
        return [e for e in self._entries if e.tier == tier]
```

- [ ] **Step 4: Run tests — verify they pass**

```
pytest tests/test_model_catalog.py -v
```
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add agent_platform/model_router/catalog.py tests/test_model_catalog.py
git commit -m "feat: add ModelEntry and ModelCatalog"
```

---

## Task 2: Default Catalog

**Files:**
- Create: `agent_platform/model_router/default_catalog.py`

- [ ] **Step 1: Create default_catalog.py**

```python
# agent_platform/model_router/default_catalog.py
from agent_platform.model_router.catalog import ModelEntry

DEFAULT_CATALOG: list[ModelEntry] = [
    # Claude Code — source: docs.anthropic.com/en/docs/about-claude/models 2026-03-17
    ModelEntry("claude-opus-4-6",    "claude_code", tier=1, context_window=1000000, tags=["reasoning", "code"]),
    ModelEntry("claude-sonnet-4-6",  "claude_code", tier=2, context_window=1000000, tags=["code", "balanced"]),
    ModelEntry("claude-haiku-4-5",   "claude_code", tier=3, context_window=200000,  tags=["fast", "router"]),

    # Codex CLI — source: platform.openai.com/docs/models + user-verified CLI screen 2026-03-17
    ModelEntry("gpt-5.4",            "codex", tier=1, context_window=1050000, tags=["reasoning", "code", "default"]),
    ModelEntry("gpt-5.3-codex",      "codex", tier=1, context_window=400000,  tags=["reasoning", "code"]),
    ModelEntry("gpt-5.2-codex",      "codex", tier=2, context_window=400000,  tags=["code", "balanced"]),
    ModelEntry("gpt-5.2",            "codex", tier=2, context_window=256000,  tags=["code", "balanced"]),
    ModelEntry("gpt-5.1-codex-max",  "codex", tier=2, context_window=400000,  tags=["reasoning", "balanced"]),
    ModelEntry("gpt-5.1-codex-mini", "codex", tier=3, context_window=400000,  tags=["fast", "router"]),

    # mycodex — local fork of Codex CLI, identical model support
    ModelEntry("gpt-5.4",            "mycodex", tier=1, context_window=1050000, tags=["reasoning", "code", "default"]),
    ModelEntry("gpt-5.3-codex",      "mycodex", tier=1, context_window=400000,  tags=["reasoning", "code"]),
    ModelEntry("gpt-5.2-codex",      "mycodex", tier=2, context_window=400000,  tags=["code", "balanced"]),
    ModelEntry("gpt-5.2",            "mycodex", tier=2, context_window=256000,  tags=["code", "balanced"]),
    ModelEntry("gpt-5.1-codex-max",  "mycodex", tier=2, context_window=400000,  tags=["reasoning", "balanced"]),
    ModelEntry("gpt-5.1-codex-mini", "mycodex", tier=3, context_window=400000,  tags=["fast", "router"]),
]
```

- [ ] **Step 2: Write a smoke test at the bottom of test_model_catalog.py**

```python
def test_default_catalog_has_all_executors():
    from agent_platform.model_router.default_catalog import DEFAULT_CATALOG
    from agent_platform.model_router.catalog import ModelCatalog
    c = ModelCatalog(DEFAULT_CATALOG)
    for executor in ("claude_code", "codex", "mycodex"):
        assert len(c.for_executor(executor)) > 0, f"no models for {executor}"
    # tier-1 exists for each executor
    for executor in ("claude_code", "codex", "mycodex"):
        assert c.best_for(executor, max_tier=1) is not None
```

- [ ] **Step 3: Run tests — verify they pass**

```
pytest tests/test_model_catalog.py -v
```
Expected: 8 passed

- [ ] **Step 4: Commit**

```bash
git add agent_platform/model_router/default_catalog.py tests/test_model_catalog.py
git commit -m "feat: add DEFAULT_CATALOG with Claude/Codex/mycodex models"
```

---

## Task 3: RoutingPolicy

**Files:**
- Create: `agent_platform/model_router/policy.py`
- Create: `tests/test_routing_policy.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_routing_policy.py
from __future__ import annotations
import pytest
from agent_platform.model_router.catalog import ModelCatalog, ModelEntry
from agent_platform.model_router.policy import RoutingPolicy

CATALOG = ModelCatalog([
    ModelEntry("strong", "codex", tier=1, context_window=100, tags=[]),
    ModelEntry("medium", "codex", tier=2, context_window=100, tags=[]),
    ModelEntry("light",  "codex", tier=3, context_window=100, tags=[]),
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
    # stage not in stage_models at all → tier-based → large→tier1 → "strong"
    assert policy().resolve("execution_loop", "large", "codex") == "strong"

def test_tier_based_small_uses_tier3():
    assert policy().resolve("execution_loop", "small", "codex") == "light"

def test_unknown_executor_falls_back_to_default():
    assert policy().resolve("execution_loop", "large", "unknown_executor") == "strong"
```

- [ ] **Step 2: Run tests — verify they fail**

```
pytest tests/test_routing_policy.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Implement policy.py**

```python
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
        stage_cfg = self._stage_models.get(stage, {})

        # 1. exact stage+complexity match
        if complexity in stage_cfg:
            return stage_cfg[complexity]

        # 2. stage default
        if "default" in stage_cfg:
            return stage_cfg["default"]

        # 3. tier-based via catalog
        if executor:
            max_tier = COMPLEXITY_MAX_TIER.get(complexity, 2)
            entry = self._catalog.best_for(executor, max_tier=max_tier)
            if entry:
                return entry.name

        # 4. final fallback
        return self._default
```

- [ ] **Step 4: Run tests — verify they pass**

```
pytest tests/test_routing_policy.py -v
```
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add agent_platform/model_router/policy.py tests/test_routing_policy.py
git commit -m "feat: add RoutingPolicy with 4-level resolution"
```

---

## Task 4: SmartRouter + AssessResult

**Files:**
- Create: `agent_platform/model_router/smart_router.py`
- Create: `tests/test_smart_router.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_smart_router.py
from __future__ import annotations
import pytest
from agent_platform.model_router.smart_router import SmartRouter, AssessResult

def router():
    return SmartRouter()

def test_explicit_complexity_field_takes_priority():
    result = router().assess({"complexity": "large", "title": "fix typo"})
    assert result.complexity == "large"
    assert result.method == "explicit"

def test_large_keyword_in_title():
    result = router().assess({"title": "重构整个认证模块", "description": ""})
    assert result.complexity == "large"
    assert result.method == "rule"

def test_small_keyword_in_title():
    result = router().assess({"title": "fix typo in README", "description": ""})
    assert result.complexity == "small"
    assert result.method == "rule"

def test_large_keyword_in_description():
    result = router().assess({"title": "update code", "description": "refactor the entire auth system"})
    assert result.complexity == "large"

def test_long_description_triggers_large():
    result = router().assess({"title": "task", "description": "x" * 501})
    assert result.complexity == "large"

def test_short_description_triggers_small():
    result = router().assess({"title": "task", "description": "fix bug"})
    assert result.complexity == "small"

def test_empty_description_triggers_small():
    result = router().assess({"title": "task", "description": ""})
    assert result.complexity == "small"

def test_missing_description_triggers_small():
    result = router().assess({"title": "task"})
    assert result.complexity == "small"

def test_medium_description_no_keywords_defaults_medium():
    desc = "implement a new endpoint that returns user data" * 3  # ~150 chars, no signals
    result = router().assess({"title": "task", "description": desc})
    assert result.complexity == "medium"
    assert result.method == "default"

def test_assess_result_has_confidence():
    result = router().assess({"complexity": "small"})
    assert 0.0 <= result.confidence <= 1.0
```

- [ ] **Step 2: Run tests — verify they fail**

```
pytest tests/test_smart_router.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Implement smart_router.py**

```python
# agent_platform/model_router/smart_router.py
from __future__ import annotations
from dataclasses import dataclass

LARGE_SIGNALS = [
    "重构", "架构", "设计", "refactor", "architect", "system", "migrate",
    "rewrite", "overhaul", "redesign", "split", "extract module",
]
SMALL_SIGNALS = [
    "修复", "fix", "typo", "rename", "add comment", "update doc",
    "bump", "format", "lint", "cleanup comment",
]
DESCRIPTION_LENGTH_LARGE = 500
DESCRIPTION_LENGTH_SMALL = 80


@dataclass
class AssessResult:
    complexity: str      # "small" | "medium" | "large"
    method: str          # "explicit" | "rule" | "default"
    confidence: float    # 0.0–1.0


class SmartRouter:
    def assess(self, task: dict) -> AssessResult:
        return _rule_assess(task)


def _rule_assess(task: dict) -> AssessResult:
    # 1. explicit field
    explicit = task.get("complexity")
    if explicit in {"small", "medium", "large"}:
        return AssessResult(explicit, method="explicit", confidence=1.0)

    title = (task.get("title") or "").lower()
    desc = (task.get("description") or "").lower()
    text = f"{title} {desc}"

    # 2. keyword signals
    if any(sig in text for sig in LARGE_SIGNALS):
        return AssessResult("large", method="rule", confidence=0.8)
    if any(sig in text for sig in SMALL_SIGNALS):
        return AssessResult("small", method="rule", confidence=0.8)

    # 3. length heuristic
    if len(desc) >= DESCRIPTION_LENGTH_LARGE:
        return AssessResult("large", method="rule", confidence=0.6)
    if len(desc) <= DESCRIPTION_LENGTH_SMALL:
        return AssessResult("small", method="rule", confidence=0.6)

    # 4. default
    return AssessResult("medium", method="default", confidence=0.5)
```

- [ ] **Step 4: Run tests — verify they pass**

```
pytest tests/test_smart_router.py -v
```
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add agent_platform/model_router/smart_router.py tests/test_smart_router.py
git commit -m "feat: add SmartRouter with rule-based complexity assessment"
```

---

## Task 5: ExecutorRegistry

**Files:**
- Create: `agent_platform/executor_layer/registry.py`
- Create: `tests/test_executor_registry.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_executor_registry.py
from __future__ import annotations
import pytest
from agent_platform.executor_layer.registry import ExecutorEntry, ExecutorRegistry


class FakeExecutor:
    def __init__(self, name): self.name = name


def make_registry():
    r = ExecutorRegistry()
    r.register(ExecutorEntry("mycodex",    FakeExecutor("mycodex"),    priority=0))
    r.register(ExecutorEntry("claude_code",FakeExecutor("claude_code"),priority=1))
    r.register(ExecutorEntry("codex",      FakeExecutor("codex"),      priority=2))
    return r


def test_ordered_returns_all_enabled_sorted_by_priority():
    r = make_registry()
    names = [e.name for e in r.ordered()]
    assert names == ["mycodex", "claude_code", "codex"]


def test_disable_excludes_from_ordered():
    r = make_registry()
    r.disable("claude_code")
    names = [e.name for e in r.ordered()]
    assert "claude_code" not in names
    assert names == ["mycodex", "codex"]


def test_enable_restores_to_ordered():
    r = make_registry()
    r.disable("mycodex")
    r.enable("mycodex")
    assert r.ordered()[0].name == "mycodex"


def test_get_returns_entry_regardless_of_enabled():
    r = make_registry()
    r.disable("codex")
    assert r.get("codex") is not None
    assert r.get("codex").enabled is False


def test_get_unknown_returns_none():
    assert make_registry().get("nonexistent") is None


def test_all_disabled_false_by_default():
    assert make_registry().all_disabled() is False


def test_all_disabled_true_when_all_off():
    r = make_registry()
    for name in ("mycodex", "claude_code", "codex"):
        r.disable(name)
    assert r.all_disabled() is True
```

- [ ] **Step 2: Run tests — verify they fail**

```
pytest tests/test_executor_registry.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Implement registry.py**

```python
# agent_platform/executor_layer/registry.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutorEntry:
    name: str
    executor: Any
    priority: int
    enabled: bool = True


class ExecutorRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, ExecutorEntry] = {}

    def register(self, entry: ExecutorEntry) -> None:
        self._entries[entry.name] = entry

    def disable(self, name: str) -> None:
        if name in self._entries:
            self._entries[name].enabled = False

    def enable(self, name: str) -> None:
        if name in self._entries:
            self._entries[name].enabled = True

    def ordered(self) -> list[ExecutorEntry]:
        return sorted(
            [e for e in self._entries.values() if e.enabled],
            key=lambda e: e.priority,
        )

    def get(self, name: str) -> ExecutorEntry | None:
        return self._entries.get(name)

    def all_disabled(self) -> bool:
        return len(self.ordered()) == 0
```

- [ ] **Step 4: Run tests — verify they pass**

```
pytest tests/test_executor_registry.py -v
```
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add agent_platform/executor_layer/registry.py tests/test_executor_registry.py
git commit -m "feat: add ExecutorRegistry with priority ordering and disable/enable"
```

---

## Task 6: FallbackChain

**Files:**
- Create: `agent_platform/executor_layer/fallback.py`
- Create: `tests/test_fallback_chain.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_fallback_chain.py
from __future__ import annotations
import pytest
from agent_platform.executor_layer.fallback import FallbackChain, ExecutorUnavailableError
from agent_platform.executor_layer.registry import ExecutorEntry, ExecutorRegistry
from agent_platform.executor_layer.executors import ExecutionResult


class SuccessExecutor:
    name = "success"
    def run(self, prompt, context=None): return ExecutionResult(True, "ok", "", 0)


class FailExecutor:
    name = "fail"
    def run(self, prompt, context=None): return ExecutionResult(False, "", "generic error", 1)


class LoginErrorExecutor:
    name = "login_fail"
    def run(self, prompt, context=None):
        return ExecutionResult(False, "", "Error: login required to continue", 1)


class QuotaErrorExecutor:
    name = "quota_fail"
    def run(self, prompt, context=None):
        return ExecutionResult(False, "", "429 quota exceeded balance", 1)


def make_registry(*executors):
    r = ExecutorRegistry()
    for i, exc in enumerate(executors):
        r.register(ExecutorEntry(exc.name, exc, priority=i))
    return r


def test_success_on_first_executor():
    r = make_registry(SuccessExecutor())
    result = FallbackChain(r).run("task", {})
    assert result.success is True
    assert result.output == "ok"


def test_falls_back_to_second_on_first_failure():
    r = make_registry(FailExecutor(), SuccessExecutor())
    result = FallbackChain(r).run("task", {})
    assert result.success is True


def test_login_error_auto_disables_executor():
    login = LoginErrorExecutor()
    r = make_registry(login, SuccessExecutor())
    FallbackChain(r).run("task", {})
    assert r.get("login_fail").enabled is False


def test_quota_error_auto_disables_executor():
    quota = QuotaErrorExecutor()
    r = make_registry(quota, SuccessExecutor())
    FallbackChain(r).run("task", {})
    assert r.get("quota_fail").enabled is False


def test_generic_failure_does_not_disable():
    fail = FailExecutor()
    r = make_registry(fail, SuccessExecutor())
    FallbackChain(r).run("task", {})
    assert r.get("fail").enabled is True


def test_all_fail_raises_executor_unavailable_error():
    r = make_registry(FailExecutor())
    with pytest.raises(ExecutorUnavailableError) as exc_info:
        FallbackChain(r).run("task", {})
    assert "fail" in exc_info.value.failures


def test_empty_registry_raises_executor_unavailable_error():
    r = ExecutorRegistry()
    with pytest.raises(ExecutorUnavailableError):
        FallbackChain(r).run("task", {})


def test_all_disabled_raises_executor_unavailable_error():
    r = make_registry(SuccessExecutor())
    r.disable("success")
    with pytest.raises(ExecutorUnavailableError):
        FallbackChain(r).run("task", {})
```

- [ ] **Step 2: Run tests — verify they fail**

```
pytest tests/test_fallback_chain.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Implement fallback.py**

```python
# agent_platform/executor_layer/fallback.py
from __future__ import annotations
from agent_platform.executor_layer.registry import ExecutorRegistry
from agent_platform.executor_layer.executors import ExecutionResult

_DISABLE_PATTERNS = (
    "login", "authenticate", "401", "unauthorized",
    "quota", "balance", "429", "rate limit",
)


class ExecutorUnavailableError(Exception):
    def __init__(self, failures: dict[str, str]) -> None:
        super().__init__(f"All executors failed: {failures}")
        self.failures = failures


class FallbackChain:
    def __init__(self, registry: ExecutorRegistry) -> None:
        self._registry = registry

    def run(self, prompt: str, context: dict | None = None, model: str = "") -> ExecutionResult:
        candidates = self._registry.ordered()
        if not candidates:
            raise ExecutorUnavailableError({})

        failures: dict[str, str] = {}
        ctx = context or {}

        for entry in candidates:
            try:
                result = entry.executor.run(prompt, ctx)
            except FileNotFoundError as e:
                self._registry.disable(entry.name)
                failures[entry.name] = f"FileNotFoundError: {e}"
                continue
            except Exception as e:
                failures[entry.name] = str(e)
                continue

            if result.success:
                return result

            reason = result.error or ""
            if any(p in reason.lower() for p in _DISABLE_PATTERNS):
                self._registry.disable(entry.name)

            failures[entry.name] = reason or f"exit_code={result.exit_code}"

        raise ExecutorUnavailableError(failures)
```

- [ ] **Step 4: Run tests — verify they pass**

```
pytest tests/test_fallback_chain.py -v
```
Expected: 8 passed

- [ ] **Step 5: Run full suite — no regressions**

```
pytest -q
```
Expected: all existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add agent_platform/executor_layer/fallback.py tests/test_fallback_chain.py
git commit -m "feat: add FallbackChain with auto-disable on login/quota errors"
```

---

## Task 7: Update AgentRuntime

**Files:**
- Modify: `agent_platform/agent_runtime/runtime.py`

- [ ] **Step 1: Update runtime.py**

Replace the existing content with:

```python
# agent_platform/agent_runtime/runtime.py
from __future__ import annotations
from agent_platform.model_router import ModelRouter


class AgentRuntime:
    def __init__(
        self,
        smart_router=None,
        routing_policy=None,
        model_router: ModelRouter | None = None,
    ) -> None:
        self._smart_router = smart_router
        self._routing_policy = routing_policy
        # legacy path: keep ModelRouter working if new components not provided
        self._legacy_router = model_router or ModelRouter()

    def run_agent(
        self,
        stage: str,
        context: dict,
        task: dict | None = None,
        executor_name: str | None = None,
    ) -> dict:
        task = task or {}
        if self._smart_router and self._routing_policy:
            assess = self._smart_router.assess(task)
            model = self._routing_policy.resolve(
                stage, assess.complexity, executor_name or ""
            )
            routing_method = assess.method
        else:
            model = self._legacy_router.model_for(
                stage=stage, task=task, executor_name=executor_name
            )
            routing_method = "legacy"

        return {
            "model": model,
            "complexity": task.get("complexity", "unknown"),
            "routing_method": routing_method,
            "stage": stage,
            "output": f"stateless_response_for_{stage}",
            "context_keys": sorted(context.keys()),
        }
```

- [ ] **Step 2: Run full test suite — no regressions**

```
pytest -q
```
Expected: all existing tests pass (AgentRuntime with no args falls back to legacy ModelRouter)

- [ ] **Step 3: Commit**

```bash
git add agent_platform/agent_runtime/runtime.py
git commit -m "feat: update AgentRuntime to accept SmartRouter+RoutingPolicy with legacy fallback"
```

---

## Task 8: Update ModelRouter to delegate to RoutingPolicy

**Files:**
- Modify: `agent_platform/model_router/router.py`

- [ ] **Step 1: Update router.py**

Keep the existing constants for backward compat. Add delegation at the bottom of `model_for`:

```python
# agent_platform/model_router/router.py
from __future__ import annotations

SUPPORTED_DEFAULT_MODEL = "gpt-5.4"

DEFAULT_MODEL_MAP = {
    "analysis": SUPPORTED_DEFAULT_MODEL,
    "planning": SUPPORTED_DEFAULT_MODEL,
    "execution_loop": SUPPORTED_DEFAULT_MODEL,
    "review": SUPPORTED_DEFAULT_MODEL,
}

LOW_COST_MODEL_MAP = {
    "analysis": "gpt-5.2-codex",
    "planning": "gpt-5.2-codex",
    "execution_loop": "gpt-5.1-codex-mini",
    "review": "gpt-5.2-codex",
}

EXECUTOR_HINT_MODEL_MAP = {
    "codex": SUPPORTED_DEFAULT_MODEL,
    "mycodex": SUPPORTED_DEFAULT_MODEL,
    "claude_code": "claude-sonnet-4-6",
}

COMPLEXITY_MODEL_OVERRIDE = {
    "small": "gpt-5.1-codex-mini",
    "medium": "gpt-5.2-codex",
    "large": SUPPORTED_DEFAULT_MODEL,
}


class ModelRouter:
    def __init__(
        self,
        budget_mode: str = "balanced",
        stage_model_map: dict[str, str] | None = None,
        routing_policy=None,   # RoutingPolicy | None — injected by Orchestrator
    ) -> None:
        self.budget_mode = budget_mode
        self.stage_model_map = dict(stage_model_map or {})
        self._policy = routing_policy

    def model_for(
        self,
        stage: str,
        task: dict | None = None,
        executor_name: str | None = None,
    ) -> str:
        # delegate to RoutingPolicy when available
        if self._policy:
            task = task or {}
            from agent_platform.model_router.smart_router import _rule_assess
            complexity = _rule_assess(task).complexity
            return self._policy.resolve(stage, complexity, executor_name or "")

        # legacy path (unchanged)
        if stage in self.stage_model_map:
            return self.stage_model_map[stage]

        task = task or {}
        if "model" in task:
            return str(task["model"])

        if task.get("complexity") in COMPLEXITY_MODEL_OVERRIDE:
            return COMPLEXITY_MODEL_OVERRIDE[str(task["complexity"])]

        if executor_name and executor_name in EXECUTOR_HINT_MODEL_MAP:
            return EXECUTOR_HINT_MODEL_MAP[executor_name]

        if self.budget_mode == "low_cost":
            return LOW_COST_MODEL_MAP.get(stage, SUPPORTED_DEFAULT_MODEL)

        return DEFAULT_MODEL_MAP.get(stage, SUPPORTED_DEFAULT_MODEL)
```

- [ ] **Step 2: Update the assertion in test_routing_and_models.py**

The existing test asserts `queue[1]["selected_model"] == "gpt-5.4"`.
With the new `COMPLEXITY_MODEL_OVERRIDE`, a `small` task now returns `"gpt-5.1-codex-mini"`.
Update the assertion:

```python
# tests/test_routing_and_models.py  — find this assertion and update it
assert queue[1]["selected_model"] == "gpt-5.1-codex-mini"
```

- [ ] **Step 3: Run full test suite**

```
pytest -q
```
Expected: all tests pass

- [ ] **Step 4: Commit**

```bash
git add agent_platform/model_router/router.py tests/test_routing_and_models.py
git commit -m "feat: update ModelRouter with real model names and RoutingPolicy delegation"
```

---

## Task 9: Wire Orchestrator

**Files:**
- Modify: `agent_platform/orchestrator/system.py`
- Modify: `agent_platform/model_router/__init__.py`
- Modify: `agent_platform/executor_layer/__init__.py`

- [ ] **Step 1: Update model_router/__init__.py**

```python
# agent_platform/model_router/__init__.py
from .router import ModelRouter
from .catalog import ModelEntry, ModelCatalog
from .default_catalog import DEFAULT_CATALOG
from .policy import RoutingPolicy
from .smart_router import SmartRouter, AssessResult

__all__ = [
    "ModelRouter", "ModelEntry", "ModelCatalog", "DEFAULT_CATALOG",
    "RoutingPolicy", "SmartRouter", "AssessResult",
]
```

- [ ] **Step 2: Update executor_layer/__init__.py**

```python
# agent_platform/executor_layer/__init__.py
from .executors import (
    ExecutorRouterV2, ExecutionResult,
    CLICodexExecutor, CLIClaudeCodeExecutor,
)
from .registry import ExecutorEntry, ExecutorRegistry
from .fallback import FallbackChain, ExecutorUnavailableError

__all__ = [
    "ExecutorRouterV2", "ExecutionResult",
    "CLICodexExecutor", "CLIClaudeCodeExecutor",
    "ExecutorEntry", "ExecutorRegistry",
    "FallbackChain", "ExecutorUnavailableError",
]
```

- [ ] **Step 3: Update orchestrator/system.py — add imports and _make_executor**

At the top of `system.py`, add these imports after the existing ones:

```python
from agent_platform.model_router import (
    ModelCatalog, DEFAULT_CATALOG, ModelEntry,
    RoutingPolicy, SmartRouter,
)
from agent_platform.executor_layer import (
    ExecutorEntry, ExecutorRegistry,
    FallbackChain, ExecutorUnavailableError,
)
```

- [ ] **Step 4: Add _make_executor helper to Orchestrator**

Add this method to the `Orchestrator` class (before `__init__`):

```python
@staticmethod
def _make_executor(name: str, repo_root, config: dict):
    from agent_platform.executor_layer import CLICodexExecutor, CLIClaudeCodeExecutor
    paths = config.get("executor_paths", {})
    live = config.get("live_cli_execution", False)
    if name == "claude_code":
        return CLIClaudeCodeExecutor(
            workdir=repo_root,
            claude_path=paths.get("claude_code", config.get("claude_path", "claude")),
            live_execution=live,
        )
    if name in ("codex", "mycodex"):
        default_bin = "mycodex" if name == "mycodex" else "codex"
        return CLICodexExecutor(
            workdir=repo_root,
            codex_path=paths.get(name, config.get("codex_path", default_bin)),
            live_execution=live,
        )
    raise ValueError(f"Unknown executor: {name}")
```

- [ ] **Step 5: Update Orchestrator.__init__ to build new components**

After the line `self.config = self._load_config(config)`, replace the block that builds
`self.executors`, `self.runtime` with:

```python
        # Build model catalog
        user_models = [ModelEntry(**e) for e in self.config.get("model_catalog", [])]
        catalog = ModelCatalog(DEFAULT_CATALOG + user_models)

        # Build executor registry
        registry = ExecutorRegistry()
        priority_list = self.config.get("executor_priority", ["mycodex", "claude_code", "codex"])
        disabled_map = self.config.get("executor_disabled", {})
        for priority, name in enumerate(priority_list):
            try:
                exc = self._make_executor(name, repo_root, self.config)
            except ValueError:
                continue
            registry.register(ExecutorEntry(
                name=name,
                executor=exc,
                priority=priority,
                enabled=not disabled_map.get(name, False),
            ))

        # Build routing components
        routing_policy = RoutingPolicy(self.config.get("stage_models", {}), catalog)
        smart_router = SmartRouter()
        self.fallback_chain = FallbackChain(registry)
        self.registry = registry

        # Keep ExecutorRouterV2 for backward compat (choose_executor still works)
        self.executors = ExecutorRouterV2(
            workdir=repo_root,
            default_executor=self.config.get("default_executor", "codex"),
            routing_mode=self.config.get("executor_routing_mode", "complexity"),
            live_execution=self.config.get("live_cli_execution", False),
            codex_path=self.config.get("codex_path", "mycodex"),
            claude_path=self.config.get("claude_path", "claude"),
        )

        # Runtime with new routing
        from agent_platform.model_router import ModelRouter
        model_router = ModelRouter(
            budget_mode=self.config.get("budget_mode", "balanced"),
            stage_model_map=self.config.get("stage_models_flat", {}),
            routing_policy=routing_policy,
        )
        self.runtime = AgentRuntime(
            smart_router=smart_router,
            routing_policy=routing_policy,
            model_router=model_router,
        )
```

- [ ] **Step 6: Update _execution_loop to catch ExecutorUnavailableError**

In `_execution_loop`, replace `execution_result = executor.run(task["title"], context)` with:

```python
                try:
                    execution_result = self.fallback_chain.run(
                        task["title"], context, model=runtime_meta.get("model", "")
                    )
                except ExecutorUnavailableError as exc:
                    task["status"] = "blocked"
                    task["result"] = {
                        "error": "all_executors_unavailable",
                        "failures": exc.failures,
                    }
                    self.store.write_text(
                        "reports/human_intervention.md",
                        self.human.build_message(
                            str(exc.failures),
                            ["check executor config", "re-enable executor"],
                        ),
                    )
                    self.state_manager.save_task_state(
                        task["id"], self._task_state_from_dict(task)
                    )
                    self.store.write_json("tasks/task_queue.json", queue)
                    continue  # move to next task, don't abort entire loop
```

- [ ] **Step 7: Run full test suite**

```
pytest -q
```
Expected: all tests pass

- [ ] **Step 8: Commit**

```bash
git add agent_platform/model_router/__init__.py agent_platform/executor_layer/__init__.py \
        agent_platform/orchestrator/system.py
git commit -m "feat: wire SmartRouter, RoutingPolicy, FallbackChain into Orchestrator"
```

---

## Task 10: CLI — disable-executor / enable-executor

**Files:**
- Modify: `agent_platform/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_cli.py`:

```python
def test_disable_executor_writes_to_config(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    store = ArtifactStore(workspace)
    store.ensure_layout()
    store.write_json("artifacts/executor_config.json", {
        "executor_priority": ["mycodex", "claude_code", "codex"],
        "executor_disabled": {"mycodex": False, "claude_code": False, "codex": False},
    })

    from agent_platform.cli import build_parser, disable_executor
    disable_executor(workspace, "claude_code")

    cfg = store.read_json("artifacts/executor_config.json", {})
    assert cfg["executor_disabled"]["claude_code"] is True
    assert cfg["executor_disabled"]["mycodex"] is False


def test_enable_executor_writes_to_config(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    store = ArtifactStore(workspace)
    store.ensure_layout()
    store.write_json("artifacts/executor_config.json", {
        "executor_disabled": {"claude_code": True},
    })

    from agent_platform.cli import enable_executor
    enable_executor(workspace, "claude_code")

    cfg = store.read_json("artifacts/executor_config.json", {})
    assert cfg["executor_disabled"]["claude_code"] is False
```

- [ ] **Step 2: Run tests — verify they fail**

```
pytest tests/test_cli.py -k "disable or enable" -v
```
Expected: `ImportError` (functions not yet defined)

- [ ] **Step 3: Add disable_executor / enable_executor functions to cli.py**

```python
def disable_executor(workspace: Path, name: str) -> None:
    store = ArtifactStore(workspace)
    cfg = store.read_json("artifacts/executor_config.json", default={})
    disabled = cfg.setdefault("executor_disabled", {})
    disabled[name] = True
    store.write_json("artifacts/executor_config.json", cfg)
    print(f"Executor '{name}' disabled.")


def enable_executor(workspace: Path, name: str) -> None:
    store = ArtifactStore(workspace)
    cfg = store.read_json("artifacts/executor_config.json", default={})
    disabled = cfg.setdefault("executor_disabled", {})
    disabled[name] = False
    store.write_json("artifacts/executor_config.json", cfg)
    print(f"Executor '{name}' enabled.")
```

- [ ] **Step 4: Add CLI subcommands to build_parser()**

```python
    disable_parser = subparsers.add_parser("disable-executor", help="Mark an executor as disabled")
    disable_parser.add_argument("--workspace", type=Path, required=True)
    disable_parser.add_argument("--name", type=str, required=True)

    enable_parser = subparsers.add_parser("enable-executor", help="Mark an executor as enabled")
    enable_parser.add_argument("--workspace", type=Path, required=True)
    enable_parser.add_argument("--name", type=str, required=True)
```

- [ ] **Step 5: Add dispatch in main()**

```python
    if args.command == "disable-executor":
        disable_executor(args.workspace, args.name)
        return

    if args.command == "enable-executor":
        enable_executor(args.workspace, args.name)
        return
```

- [ ] **Step 6: Update init_workspace to write new config schema**

In `init_workspace()`, replace the executor_config.json default with:

```python
    if not (workspace / "artifacts" / "executor_config.json").exists():
        store.write_json(
            "artifacts/executor_config.json",
            {
                "executor_priority": ["mycodex", "claude_code", "codex"],
                "executor_disabled": {"mycodex": False, "claude_code": False, "codex": False},
                "executor_paths": {"mycodex": "mycodex", "claude_code": "claude", "codex": "codex"},
                "live_cli_execution": False,
                "stage_models": {
                    "analysis":       {"small": "gpt-5.2-codex", "medium": "gpt-5.4", "large": "gpt-5.4"},
                    "planning":       {"default": "gpt-5.4"},
                    "execution_loop": {"small": "gpt-5.1-codex-mini", "medium": "gpt-5.2-codex", "large": "gpt-5.4"},
                    "review":         {"default": "gpt-5.2-codex"},
                },
                "model_catalog": [],
                "budget_mode": "balanced",
            },
        )
```

- [ ] **Step 7: Run full test suite**

```
pytest -q
```
Expected: all tests pass

- [ ] **Step 8: Commit**

```bash
git add agent_platform/cli.py tests/test_cli.py
git commit -m "feat: add disable-executor / enable-executor CLI subcommands"
```

---

## Final Verification

- [ ] **Run complete test suite**

```
pytest -v
```
Expected: all tests pass, no regressions

- [ ] **Smoke test the CLI**

```bash
agent-platform init-workspace .test_ws
cat .test_ws/artifacts/executor_config.json
agent-platform disable-executor --workspace .test_ws --name claude_code
cat .test_ws/artifacts/executor_config.json
# verify claude_code: true
agent-platform enable-executor --workspace .test_ws --name claude_code
rm -rf .test_ws
```

- [ ] **Final commit**

```bash
git add -A
git commit -m "feat: complete smart routing layer implementation"
```

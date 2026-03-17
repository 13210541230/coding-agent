# Smart Routing Layer Design

**Date:** 2026-03-17
**Status:** Approved
**Scope:** CLI-based executor routing with intelligent model selection

---

## 1. Goals

- Replace stub `AgentRuntime` / placeholder `ModelRouter` with a real, working routing layer
- Support `claude_code`, `codex`, and `mycodex` (local codex fork) CLI executors with automatic fallback
- Route per workflow stage to the most appropriate model based on task complexity
- Provide a model catalog with capability tiers for maintainable configuration
- Remain extensible for future third-party API executors

---

## 2. Architecture Overview

```
Task
  → SmartRouter.assess(task)                           # AssessResult(complexity, method)
  → RoutingPolicy.resolve(stage, complexity, executor) # model name string
  → FallbackChain.run(prompt, context, model)          # tries executors in priority order
  → ExecutionResult
```

### New Files

```
agent_platform/
  model_router/
    catalog.py            ModelEntry, ModelCatalog
    default_catalog.py    Built-in model table
    policy.py             RoutingPolicy
    smart_router.py       SmartRouter, AssessResult (defined here)
  executor_layer/
    registry.py           ExecutorEntry, ExecutorRegistry
    fallback.py           FallbackChain, ExecutorUnavailableError
```

### Modified Files (minimal changes)

```
agent_platform/model_router/router.py       ModelRouter delegates to RoutingPolicy internally;
                                            public interface (model_for) preserved unchanged
agent_platform/executor_layer/executors.py  ExecutorRouterV2.choose_executor delegates to Registry;
                                            CLICodexExecutor/CLIClaudeCodeExecutor internals unchanged
agent_platform/agent_runtime/runtime.py     AgentRuntime stores SmartRouter + RoutingPolicy directly
agent_platform/orchestrator/system.py       Wires new modules at init; _make_executor() helper added
agent_platform/cli.py                       Adds disable-executor / enable-executor subcommands
```

**ModelRouter role clarification:** `ModelRouter` retains its public `model_for()` interface.
Internally it delegates to `RoutingPolicy`. `AgentRuntime` receives `SmartRouter` and
`RoutingPolicy` directly at construction — it no longer accepts a `ModelRouter` instance.
The old `AgentRuntime(model_router=...)` signature is removed; existing tests that construct
`AgentRuntime()` with no arguments continue to work via a default no-op policy.

---

## 3. ModelCatalog

### ModelEntry

```python
@dataclass
class ModelEntry:
    name: str            # identifier passed to CLI (e.g. "claude-sonnet-4-6")
    executor: str        # "claude_code" | "codex" | "third_party"
    tier: int            # 1=strongest/most expensive, 4=lightest/cheapest
    context_window: int  # token limit
    tags: list[str]      # ["reasoning", "code", "fast", "router"]
```

### Capability Tiers

| Tier | Description | Examples |
|------|-------------|---------|
| 1 | Strongest reasoning (most expensive) | claude-opus-4-6, gpt-5.4, o3 |
| 2 | Balanced capability | claude-sonnet-4-6, o4-mini, o3-mini |
| 3 | Lightweight / fast | claude-haiku-4-5, codex-mini-latest |
| 4 | Minimal / router use | reserved for future local models |

### Complexity → Max Tier Mapping

| Complexity | max_tier passed to catalog.best_for() |
|------------|--------------------------------------|
| small      | 3 |
| medium     | 2 |
| large      | 1 |

This mapping is used by `RoutingPolicy` when no exact model name is configured for a
stage+complexity combination.

### Built-in Default Catalog (`default_catalog.py`)

```python
DEFAULT_CATALOG = [
    # Claude Code (claude CLI)
    # Source: Anthropic API docs 2026-03-17
    ModelEntry("claude-opus-4-6",    "claude_code", tier=1, context_window=200000, tags=["reasoning","code"]),
    ModelEntry("claude-sonnet-4-6",  "claude_code", tier=2, context_window=200000, tags=["code","balanced"]),
    ModelEntry("claude-haiku-4-5",   "claude_code", tier=3, context_window=200000, tags=["fast","router"]),

    # Codex CLI (codex) — default model is o4-mini per Codex CLI config.toml
    # Source: openai-python SDK v2.28.0, Codex CLI README 2026-03-17
    ModelEntry("gpt-5.4",            "codex", tier=1, context_window=1000000, tags=["reasoning","code"]),
    ModelEntry("o3",                 "codex", tier=1, context_window=200000,  tags=["reasoning"]),
    ModelEntry("o4-mini",            "codex", tier=2, context_window=200000,  tags=["code","balanced","default"]),
    ModelEntry("o3-mini",            "codex", tier=2, context_window=200000,  tags=["reasoning","balanced"]),
    ModelEntry("codex-mini-latest",  "codex", tier=3, context_window=128000,  tags=["fast","router"]),

    # mycodex — local fork of Codex CLI, installed as `mycodex`
    # Identical model support to codex; registered as a separate executor.
    ModelEntry("gpt-5.4",            "mycodex", tier=1, context_window=1000000, tags=["reasoning","code"]),
    ModelEntry("o3",                 "mycodex", tier=1, context_window=200000,  tags=["reasoning"]),
    ModelEntry("o4-mini",            "mycodex", tier=2, context_window=200000,  tags=["code","balanced","default"]),
    ModelEntry("o3-mini",            "mycodex", tier=2, context_window=200000,  tags=["reasoning","balanced"]),
    ModelEntry("codex-mini-latest",  "mycodex", tier=3, context_window=128000,  tags=["fast","router"]),
]
```

**`mycodex` executor note:** Local fork of Codex CLI with extended capabilities.
Model pool is identical to `codex`. Registered via `CLICodexExecutor(codex_path="mycodex")`.
Default priority chain: `mycodex` → `claude_code` → `codex` (mycodex preferred as
the enhanced local path; claude_code second; upstream codex as final fallback).

### ModelCatalog API

```python
class ModelCatalog:
    def for_executor(self, executor: str) -> list[ModelEntry]          # sorted by tier asc
    def best_for(self, executor: str, max_tier: int = 4) -> ModelEntry | None
    def by_tier(self, tier: int) -> list[ModelEntry]                   # cross-executor
```

User extensions via `executor_config.json` → `model_catalog` key (merged at init,
user entries override built-ins with the same `name` + `executor` combination):
```json
{ "model_catalog": [
    { "name": "my-local", "executor": "third_party", "tier": 4,
      "context_window": 8000, "tags": ["fast"] }
] }
```

---

## 4. ExecutorRegistry + FallbackChain

### ExecutorRegistry

```python
# executor_layer/registry.py

@dataclass
class ExecutorEntry:
    name: str
    executor: Any      # CLICodexExecutor | CLIClaudeCodeExecutor | future
    priority: int      # lower integer = higher priority
    enabled: bool = True

class ExecutorRegistry:
    def register(self, entry: ExecutorEntry) -> None
    def disable(self, name: str) -> None    # disables in memory; caller persists to config
    def enable(self, name: str) -> None
    def ordered(self) -> list[ExecutorEntry]   # sorted by priority asc, enabled entries only
    def get(self, name: str) -> ExecutorEntry | None
    def all_disabled(self) -> bool             # True when ordered() returns []
```

**Persistence:** `disable()` / `enable()` modify the in-memory registry only.
The `Orchestrator` is responsible for writing the updated `executor_disabled` map
back to `artifacts/executor_config.json` after any state change (auto-disable or
CLI command). The CLI `disable-executor` subcommand: reads config → calls
`registry.disable(name)` → writes `executor_disabled[name] = true` to config file.

### FallbackChain

```python
# executor_layer/fallback.py

class ExecutorUnavailableError(Exception):
    """Raised when all executors are exhausted. Carries per-executor failure reasons."""
    def __init__(self, failures: dict[str, str]): ...
    failures: dict[str, str]   # {executor_name: reason_string}

class FallbackChain:
    def __init__(self, registry: ExecutorRegistry): ...

    def run(self, prompt: str, context: dict, model: str = "") -> ExecutionResult:
        """
        1. candidates = registry.ordered()
        2. If candidates is empty → raise ExecutorUnavailableError({})
        3. For each entry in candidates:
             a. Call entry.executor.run(prompt, context)  — pass model hint via context
             b. If ExecutionResult.success → return immediately
             c. If failure: classify error (see table below)
                - DISABLE errors: call registry.disable(name), record failure, continue
                - NON-DISABLE errors: record failure, continue
        4. All candidates exhausted → raise ExecutorUnavailableError(failures)
        """
```

### Failure Classification

| Condition | Detected via | Auto-disable | Action |
|-----------|-------------|-------------|--------|
| `stderr` contains `login` / `authenticate` / `401` / `unauthorized` | string match | Yes | disable + next |
| `stderr` contains `quota` / `balance` / `429` / `rate limit` | string match | Yes | disable + next |
| `FileNotFoundError` (CLI not found) | exception type | Yes | disable + next |
| `subprocess.TimeoutExpired` | exception type | No | record + next |
| `returncode != 0`, stderr does NOT match any disable pattern | exit code check | No | record + next |

**Note:** A non-zero exit code from a real code task (e.g., tests failed) is a task
failure, not an executor failure — the executor itself is working. Only the patterns
above indicate the executor is unavailable.

**All-disabled exhaustion:** When `FallbackChain.run()` finds `registry.ordered()` is
empty (either initially or after disabling the last executor mid-chain), it raises
`ExecutorUnavailableError`. The caller (`Orchestrator._execution_loop`) must catch this
and route to `HumanIntervention`, marking the task as `"blocked"`.

---

## 5. SmartRouter

### AssessResult (defined in `smart_router.py`)

```python
@dataclass
class AssessResult:
    complexity: str    # "small" | "medium" | "large"
    method: str        # "explicit" | "rule" | "default"
    confidence: float  # 0.0–1.0; rule matches = 0.8, default = 0.5
```

### Single-Pass Rules Assessment

> **RouterModelChain (calling a real LLM for routing) is deferred to a follow-on spec.**
> This iteration uses rules only. Adding a remote model call for every task dispatch
> would introduce latency, token cost, and circular dependency risk with no clear
> accuracy benefit over well-defined rules.

```python
LARGE_SIGNALS = [
    "重构", "架构", "设计", "refactor", "architect", "system", "migrate",
    "rewrite", "overhaul", "redesign", "split", "extract module",
]
SMALL_SIGNALS = [
    "修复", "fix", "typo", "rename", "add comment", "update doc",
    "bump", "format", "lint", "cleanup comment",
]
DESCRIPTION_LENGTH_LARGE = 500   # chars; descriptions longer than this → large
DESCRIPTION_LENGTH_SMALL = 80    # chars; descriptions shorter than this → small (if no LARGE signals)

def _rule_assess(task: dict) -> AssessResult:
    # Priority 1: explicit complexity field in task dict
    if "complexity" in task and task["complexity"] in {"small", "medium", "large"}:
        return AssessResult(task["complexity"], method="explicit", confidence=1.0)

    title = (task.get("title") or "").lower()
    desc  = (task.get("description") or "").lower()
    text  = f"{title} {desc}"

    # Priority 2: signal keywords
    if any(sig in text for sig in LARGE_SIGNALS):
        return AssessResult("large", method="rule", confidence=0.8)
    if any(sig in text for sig in SMALL_SIGNALS):
        return AssessResult("small", method="rule", confidence=0.8)

    # Priority 3: description length heuristic
    if len(desc) >= DESCRIPTION_LENGTH_LARGE:
        return AssessResult("large", method="rule", confidence=0.6)
    if len(desc) <= DESCRIPTION_LENGTH_SMALL:
        return AssessResult("small", method="rule", confidence=0.6)

    # Default
    return AssessResult("medium", method="default", confidence=0.5)
```

### SmartRouter API

```python
class SmartRouter:
    def __init__(self, registry: ExecutorRegistry): ...

    def assess(self, task: dict) -> AssessResult:
        return _rule_assess(task)
```

---

## 6. RoutingPolicy

### Resolution Priority

```
1. stage_models[stage][complexity]          exact name match → return name
2. stage_models[stage]["default"]           stage default name → return name
3. catalog.best_for(executor, max_tier)     tier-based (see §3 complexity→tier table)
4. default_model ("gpt5.4")                 final fallback
```

Where "executor" in step 3 is the name of the first enabled executor in the registry
(the one `FallbackChain` will try first).

### RoutingPolicy API

```python
class RoutingPolicy:
    def __init__(
        self,
        stage_models: dict,
        catalog: ModelCatalog,
        default_model: str = "gpt5.4",
    ): ...

    def resolve(self, stage: str, complexity: str, executor: str = "") -> str:
        """Returns a model name string."""
```

### Config Schema (stage_models)

```json
{
  "stage_models": {
    "analysis": {
      "small":   "gpt5.4-medium",
      "medium":  "gpt5.4",
      "large":   "gpt5.4"
    },
    "planning":       { "default": "gpt5.4" },
    "execution_loop": {
      "small":   "gpt5.4-mini",
      "medium":  "gpt5.4-medium",
      "large":   "gpt5.4"
    },
    "review":         { "default": "gpt5.4-medium" }
  }
}
```

---

## 7. Full Config Schema (`artifacts/executor_config.json`)

```json
{
  "executor_priority": ["mycodex", "claude_code", "codex"],

  "executor_disabled": {
    "mycodex": false,
    "claude_code": false,
    "codex": false
  },

  "executor_paths": {
    "mycodex": "mycodex",
    "claude_code": "claude",
    "codex": "codex"
  },

  "live_cli_execution": true,

  "stage_models": {
    "analysis":       { "small": "gpt5.4-medium", "medium": "gpt5.4", "large": "gpt5.4" },
    "planning":       { "default": "gpt5.4" },
    "execution_loop": { "small": "gpt5.4-mini", "medium": "gpt5.4-medium", "large": "gpt5.4" },
    "review":         { "default": "gpt5.4-medium" }
  },

  "model_catalog": [],

  "budget_mode": "balanced"
}
```

**Migration from old flat keys:** `codex_path` and `claude_path` top-level keys remain
supported for one release as fallback. `executor_paths` takes precedence if present.
`init-workspace` will write `executor_paths` going forward.

---

## 8. Orchestrator Wiring

```python
# orchestrator/system.py  — after _load_config()

from agent_platform.model_router.catalog import ModelCatalog
from agent_platform.model_router.default_catalog import DEFAULT_CATALOG
from agent_platform.model_router.policy import RoutingPolicy
from agent_platform.model_router.smart_router import SmartRouter
from agent_platform.executor_layer.registry import ExecutorRegistry, ExecutorEntry
from agent_platform.executor_layer.fallback import FallbackChain

def _make_executor(name: str, config: dict):
    paths = config.get("executor_paths", {})
    live  = config.get("live_cli_execution", False)
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

# Build catalog
catalog = ModelCatalog(DEFAULT_CATALOG + [
    ModelEntry(**e) for e in config.get("model_catalog", [])
])

# Build registry
registry = ExecutorRegistry()
for priority, name in enumerate(config.get("executor_priority", ["claude_code", "codex"])):
    registry.register(ExecutorEntry(
        name=name,
        executor=_make_executor(name, config),
        priority=priority,
        enabled=not config.get("executor_disabled", {}).get(name, False),
    ))

# Build routing components
self.routing_policy = RoutingPolicy(config.get("stage_models", {}), catalog)
self.smart_router   = SmartRouter(registry)
self.fallback_chain = FallbackChain(registry)
```

### AgentRuntime Changes

```python
# agent_runtime/runtime.py

class AgentRuntime:
    def __init__(
        self,
        smart_router: SmartRouter | None = None,
        routing_policy: RoutingPolicy | None = None,
        model_router: ModelRouter | None = None,   # kept for backward compat, ignored if new args present
    ): ...

    def run_agent(self, stage, context, task=None, executor_name=None):
        task = task or {}
        if self.smart_router and self.routing_policy:
            assess = self.smart_router.assess(task)
            model  = self.routing_policy.resolve(stage, assess.complexity, executor_name or "")
            routing_method = assess.method
        else:
            # fallback to old ModelRouter path
            model = self.router.model_for(stage=stage, task=task, executor_name=executor_name)
            routing_method = "legacy"

        return {
            "model":          model,
            "complexity":     task.get("complexity", "unknown"),
            "routing_method": routing_method,
            "stage":          stage,
            "output":         f"stateless_response_for_{stage}",
        }
```

### Orchestrator._execution_loop Error Handling Addition

```python
from agent_platform.executor_layer.fallback import ExecutorUnavailableError

try:
    execution_result = self.fallback_chain.run(task["title"], context, model=runtime_meta["model"])
except ExecutorUnavailableError as e:
    task["status"] = "blocked"
    task["result"] = {"error": "all_executors_unavailable", "failures": e.failures}
    self.store.write_text("reports/human_intervention.md",
        self.human.build_message(str(e.failures), ["check executor config", "re-enable executor"]))
    continue
```

---

## 9. CLI Additions

```bash
# Mark executor as disabled — writes executor_disabled[name]=true to executor_config.json
agent-platform disable-executor --name claude_code --workspace my_workspace

# Re-enable — writes executor_disabled[name]=false
agent-platform enable-executor --name claude_code --workspace my_workspace
```

Both commands reload the config file, apply the change, and write it back atomically.

---

## 10. Testing Strategy

| Test File | Components Covered | Key Invariants |
|-----------|-------------------|----------------|
| `test_model_catalog.py` | `ModelCatalog`, `ModelEntry` | `best_for` returns lowest tier ≤ max_tier; user entries override built-ins by name |
| `test_routing_policy.py` | `RoutingPolicy` | exact→default→tier→fallback resolution order; tier-based uses complexity→max_tier table |
| `test_smart_router.py` | `SmartRouter`, `_rule_assess` | keywords→large/small; length thresholds; explicit field takes priority; empty desc→small |
| `test_executor_registry.py` | `ExecutorRegistry` | `ordered()` excludes disabled; priority sort order; `all_disabled()` |
| `test_fallback_chain.py` | `FallbackChain`, `ExecutorUnavailableError` | success on first try; single failure → degradation to next; login/quota stderr → auto-disable; timeout → no disable; all-exhausted → raises with failures dict |
| `test_cli.py` (extended) | `disable-executor` / `enable-executor` CLI | round-trip: invoke CLI → reload config → confirm executor excluded from ordered() |

All tests use `tempfile` + mock executors. No real CLI calls required.

---

## 11. What Does NOT Change

- `WorkflowState`, `StateManagerV2`, `GateController` — untouched
- `CLICodexExecutor` / `CLIClaudeCodeExecutor` class internals — untouched
- `ModelRouter.model_for()` public signature — preserved (delegates to `RoutingPolicy` internally)
- `ExecutorRouterV2.choose_executor()` public signature — preserved (delegates to `Registry` internally)
- All 38 existing tests — continue to pass without modification

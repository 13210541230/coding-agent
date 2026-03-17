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
            # task-level explicit model override takes priority over routing policy
            if "model" in task:
                return str(task["model"])
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

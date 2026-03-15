from __future__ import annotations

DEFAULT_MODEL_MAP = {
    "analysis": "gpt-4.1",
    "planning": "gpt-4.1",
    "execution_loop": "gpt-4.1-mini",
    "review": "gpt-4.1",
}

LOW_COST_MODEL_MAP = {
    "analysis": "gpt-4.1-mini",
    "planning": "gpt-4.1-mini",
    "execution_loop": "gpt-4.1-nano",
    "review": "gpt-4.1-mini",
}

EXECUTOR_HINT_MODEL_MAP = {
    "codex": "gpt-4.1-nano",
    "claude_code": "claude-3-5-sonnet",
}

COMPLEXITY_MODEL_OVERRIDE = {
    "small": "gpt-4.1-nano",
    "medium": "gpt-4.1-mini",
    "large": "gpt-4.1",
}


class ModelRouter:
    def __init__(self, budget_mode: str = "balanced", stage_model_map: dict[str, str] | None = None) -> None:
        self.budget_mode = budget_mode
        self.stage_model_map = dict(stage_model_map or {})

    def model_for(self, stage: str, task: dict | None = None, executor_name: str | None = None) -> str:
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
            return LOW_COST_MODEL_MAP.get(stage, "gpt-4.1-mini")

        return DEFAULT_MODEL_MAP.get(stage, "gpt-4.1-mini")

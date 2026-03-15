from __future__ import annotations

from agent_platform.model_router import ModelRouter


class AgentRuntime:
    def __init__(self, model_router: ModelRouter | None = None) -> None:
        self.router = model_router or ModelRouter()

    def run_agent(self, stage: str, context: dict, task: dict | None = None, executor_name: str | None = None) -> dict:
        model = self.router.model_for(stage=stage, task=task, executor_name=executor_name)
        return {
            "model": model,
            "stage": stage,
            "output": f"stateless_response_for_{stage}",
            "context_keys": sorted(context.keys()),
        }

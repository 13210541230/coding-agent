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
            # task-level explicit model override takes priority over routing policy
            if "model" in task:
                model = str(task["model"])
                routing_method = "explicit"
            else:
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

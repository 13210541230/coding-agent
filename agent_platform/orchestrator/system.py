from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from agent_platform.agent_runtime import AgentRuntime
from agent_platform.artifact_store import ArtifactStore
from agent_platform.context_engine import ContextEngineV2
from agent_platform.executor_layer import ExecutorRouterV2
from agent_platform.failure_analyzer import FailureAnalyzer
from agent_platform.gate_controller import GateController
from agent_platform.human_intervention import HumanIntervention
from agent_platform.memory_system import MemorySystem
from agent_platform.model_router import ModelRouter
from agent_platform.retry_controller import RetryController
from agent_platform.state_manager import StateManagerV2
from agent_platform.types import Checkpoint, Step, Summary, TaskState, WorkflowStateV2
from agent_platform.workflow_engine import WorkflowEngine
from agent_platform.model_router import (
    ModelCatalog, DEFAULT_CATALOG, ModelEntry,
    RoutingPolicy, SmartRouter,
)
from agent_platform.executor_layer import (
    ExecutorEntry, ExecutorRegistry,
    FallbackChain, ExecutorUnavailableError,
)


class Orchestrator:
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

    def __init__(self, workspace: Path, repo_root: Path, config: dict | None = None):
        self.store = ArtifactStore(workspace)
        self.store.ensure_layout()
        self.state_manager = StateManagerV2(workspace)
        self.workflow_engine = WorkflowEngine()
        self.memory = MemorySystem(self.store)
        self.config = self._load_config(config)
        self.context_engine = ContextEngineV2(self.store, self.memory)
        self.failures = FailureAnalyzer()
        self.retries = RetryController()
        self.human = HumanIntervention()
        self.gates = GateController(self.store)

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
        self.repo_root = repo_root

    def _load_config(self, config: dict | None) -> dict:
        base = {
            "default_executor": "codex",
            "executor_routing_mode": "complexity",
            "budget_mode": "balanced",
            "stage_models": {},
            "live_cli_execution": False,
            "codex_path": "mycodex",
            "claude_path": "mycodex",
        }
        file_cfg = self.store.read_json("artifacts/executor_config.json", default={})
        return {**base, **file_cfg, **(config or {})}

    def run(self, workflow: str, resume: bool = True) -> None:
        state = self.state_manager.load_workflow_state() if resume else None
        if state and state.workflow == workflow:
            start_idx = self.workflow_engine.resume_index(workflow, state.current_phase)
            completed = set(state.completed)
        else:
            state = WorkflowStateV2(
                workflow=workflow,
                current_phase=self.workflow_engine.steps_for(workflow)[0].value,
            )
            start_idx = 0
            completed = set()

        for step in self.workflow_engine.steps_for(workflow)[start_idx:]:
            if step.value in completed:
                continue

            state.current_phase = step.value
            state.updated_at = datetime.now()
            self.state_manager.save_workflow_state(state)

            result = self._run_step(step, workflow)
            state.completed.append(step.value)
            state.updated_at = datetime.now()
            self.state_manager.save_workflow_state(state)
            self.state_manager.save_checkpoint(
                step.value,
                Checkpoint(phase=step.value, result=result),
            )

        self.state_manager.save_summary(
            Summary(
                current_phase=state.current_phase,
                last_result={"workflow": workflow, "completed_phases": list(state.completed)},
                next_phase="",
                completed=True,
            )
        )

    def _run_step(self, step: Step, workflow: str) -> dict[str, Any]:
        handlers = {
            Step.INSTRUCTION_ENHANCE: self._instruction_enhance,
            Step.ANALYSIS: self._analysis,
            Step.PLANNING: self._planning,
            Step.TASK_SPLIT: self._task_split,
            Step.EXECUTION_LOOP: self._execution_loop,
            Step.REVIEW: self._review,
        }
        result = handlers[step]()
        next_phase = self._next_phase(step, workflow)
        self.state_manager.save_summary(
            Summary(
                current_phase=step.value,
                last_result=result,
                next_phase=next_phase,
                completed=next_phase == "",
            )
        )
        return result

    def _next_phase(self, current: Step, workflow: str) -> str:
        steps = self.workflow_engine.steps_for(workflow)
        for index, step in enumerate(steps):
            if step == current:
                return steps[index + 1].value if index + 1 < len(steps) else ""
        return ""

    def _instruction_enhance(self) -> dict[str, Any]:
        base_instruction = self.store.read_text("artifacts/instruction.md", default="Build requested system")
        enhanced = f"Enhanced instruction:\n{base_instruction}\n\nConstraint: orchestrator controls flow."
        self.store.write_text("artifacts/instruction.md", enhanced)
        self.state_manager.save_artifact("instruction_enhance", "instruction", {"content": enhanced})
        return {"instruction_path": "artifacts/instruction.md"}

    def _analysis(self) -> dict[str, Any]:
        instruction = self.store.read_text("artifacts/instruction.md", default="Build requested system")
        result = self.runtime.run_agent("analysis", {"instruction": instruction})
        analysis_text = f"# Analysis\n\n{result['output']}\n"
        self.store.write_text("artifacts/analysis.md", analysis_text)
        self.state_manager.save_artifact("analysis", "report", {"content": analysis_text, "model": result["model"]})
        return {"analysis_path": "artifacts/analysis.md", "model": result["model"]}

    def _planning(self) -> dict[str, Any]:
        analysis = self.store.read_text("artifacts/analysis.md")
        runtime_meta = self.runtime.run_agent("planning", {"analysis": analysis})
        plan = {
            "goals": ["build workflow engine", "add execution loop", "add retry/human intervention"],
            "tasks": [
                {"id": "task_1", "title": "Scaffold orchestration modules", "complexity": "small"},
                {"id": "task_2", "title": "Implement execution loop", "complexity": "large"},
            ],
            "model": runtime_meta["model"],
        }
        self.store.write_json("artifacts/plan.json", plan)
        self.state_manager.save_artifact("planning", "plan", plan)
        return {"task_count": len(plan["tasks"]), "model": runtime_meta["model"]}

    def _task_split(self) -> dict[str, Any]:
        plan = self.store.read_json("artifacts/plan.json", default={})
        queue = []
        for task in plan.get("tasks", []):
            task_record = {
                "id": task["id"],
                "title": task["title"],
                "description": task.get("description", task["title"]),
                "complexity": task.get("complexity", "small"),
                "retries": 0,
                "status": "pending",
            }
            queue.append(task_record)
            self.state_manager.save_task_state(task_record["id"], self._task_state_from_dict(task_record))

        self.store.write_json("tasks/task_queue.json", queue)
        self.state_manager.save_artifact("task_split", "task_queue", queue)
        return {"task_count": len(queue)}

    def _execution_loop(self) -> dict[str, Any]:
        queue = self.store.read_json("tasks/task_queue.json", default=[])
        error_history: list[str] = []

        for task in queue:
            self.state_manager.save_task_state(task["id"], self._task_state_from_dict(task))
            if task.get("status") == "done":
                continue

            while task.get("status") not in {"done", "aborted", "blocked"}:
                context = self.context_engine.build(task, repo_root=self.repo_root)
                executor = self.executors.choose_executor(task)
                runtime_meta = self.runtime.run_agent(
                    "execution_loop",
                    {"task": task, "context_summary": {"files": len(context.get("relevant_files", []))}},
                    task=task,
                    executor_name=executor.name,
                )

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
                task["selected_model"] = runtime_meta["model"]
                task["selected_executor"] = executor.name
                patch = execution_result.output or f"# patch for {task['id']} by {executor.name}\n"
                self.store.write_text(f"patches/{task['id']}.patch", patch)

                result = self._run_tests(task, execution_result)
                if result["ok"]:
                    task["status"] = "done"
                    task["result"] = {"patch_path": f"patches/{task['id']}.patch", "model": runtime_meta["model"]}
                    self.memory.record_episode(task["id"], {"task": task, "result": "success"})
                else:
                    task["retries"] = task.get("retries", 0) + 1
                    error_history.append(result["output"])
                    analysis = self.failures.analyze(result["output"], error_history)
                    self.memory.record_lesson(analysis.root_cause, analysis.fix_suggestion)
                    decision = self.retries.decide(task["retries"])
                    task["result"] = {
                        "error": result["output"],
                        "root_cause": analysis.root_cause,
                        "decision": decision.action,
                    }

                    if decision.action == "abort":
                        task["status"] = "aborted"
                    elif decision.action == "human_hint" and self.human.should_trigger(
                        same_error_count=error_history.count(result["output"]),
                        same_file_edit_count=task["retries"],
                        identical_stacktrace=analysis.stuck,
                    ):
                        msg = self.human.build_message(result["output"], ["retry", "reflection", "request hint"])
                        self.store.write_text("reports/human_intervention.md", msg)
                        self.gates.request_intervention(task["id"], result["output"], {"task": task})
                        task["status"] = "blocked"

                self.state_manager.save_task_state(task["id"], self._task_state_from_dict(task))
                self.store.write_json("tasks/task_queue.json", queue)

                if task.get("status") in {"done", "aborted", "blocked"}:
                    break

        self.state_manager.save_artifact("execution_loop", "task_queue", queue)
        done = sum(1 for task in queue if task.get("status") == "done")
        return {"completed_tasks": done, "total_tasks": len(queue)}

    def _run_tests(self, task: dict[str, Any], execution_result: Any | None = None) -> dict[str, Any]:
        if execution_result is not None and not execution_result.success:
            return {"ok": False, "output": execution_result.error or "executor failed"}
        if "fail" in task["title"].lower():
            return {"ok": False, "output": "FAIL: simulated failing task"}
        return {"ok": True, "output": "PASS"}

    def _review(self) -> dict[str, Any]:
        queue = self.store.read_json("tasks/task_queue.json", default=[])
        done = sum(1 for task in queue if task.get("status") == "done")
        total = len(queue)
        review_body = f"# Review\n\nCompleted {done}/{total} tasks.\n"
        self.store.write_text("reports/review.md", review_body)
        self.store.write_text("reports/test_report.md", "All simulated checks complete.\n")
        self.state_manager.save_artifact("review", "summary", {"done": done, "total": total})
        return {"done": done, "total": total}

    def _task_state_from_dict(self, task: dict[str, Any]) -> TaskState:
        return TaskState(
            id=task["id"],
            title=task["title"],
            status=task.get("status", "pending"),
            retries=task.get("retries", 0),
            result=task.get("result", {}),
        )

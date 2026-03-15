from __future__ import annotations

from pathlib import Path

from agent_platform.agent_runtime import AgentRuntime
from agent_platform.artifact_store import ArtifactStore
from agent_platform.context_engine import ContextEngine
from agent_platform.executor_layer import ExecutorRouter
from agent_platform.failure_analyzer import FailureAnalyzer
from agent_platform.human_intervention import HumanIntervention
from agent_platform.memory_system import MemorySystem
from agent_platform.model_router import ModelRouter
from agent_platform.retry_controller import RetryController
from agent_platform.state_manager import StateManager
from agent_platform.types import Step, WorkflowState
from agent_platform.workflow_engine import WorkflowEngine


class Orchestrator:
    def __init__(self, workspace: Path, repo_root: Path, config: dict | None = None):
        self.store = ArtifactStore(workspace)
        self.store.ensure_layout()
        self.state_manager = StateManager(self.store)
        self.workflow_engine = WorkflowEngine()
        self.memory = MemorySystem(self.store)
        self.config = self._load_config(config)
        self.context_engine = ContextEngine(self.store, self.memory)
        self.executors = ExecutorRouter(
            default_executor=self.config.get("default_executor", "codex"),
            routing_mode=self.config.get("executor_routing_mode", "complexity"),
        )
        self.failures = FailureAnalyzer()
        self.retries = RetryController()
        self.human = HumanIntervention()
        model_router = ModelRouter(
            budget_mode=self.config.get("budget_mode", "balanced"),
            stage_model_map=self.config.get("stage_models", {}),
        )
        self.runtime = AgentRuntime(model_router=model_router)
        self.repo_root = repo_root


    def _load_config(self, config: dict | None) -> dict:
        base = {
            "default_executor": "codex",
            "executor_routing_mode": "complexity",
            "budget_mode": "balanced",
            "stage_models": {},
        }
        file_cfg = self.store.read_json("artifacts/executor_config.json", default={})
        merged = {**base, **file_cfg, **(config or {})}
        return merged
    def run(self, workflow: str, resume: bool = True) -> None:
        state = self.state_manager.load() if resume else None
        if state and state.workflow == workflow:
            start_idx = self.workflow_engine.resume_index(workflow, state.current_step)
            completed = set(state.completed)
        else:
            state = WorkflowState(workflow=workflow, current_step=self.workflow_engine.steps_for(workflow)[0].value, completed=[])
            start_idx = 0
            completed = set()

        steps = self.workflow_engine.steps_for(workflow)
        for step in steps[start_idx:]:
            state.current_step = step.value
            self.state_manager.save(state)
            if step.value in completed:
                continue
            self._run_step(step)
            state.completed.append(step.value)
            completed.add(step.value)
            self.state_manager.save(state)

    def _run_step(self, step: Step) -> None:
        handlers = {
            Step.INSTRUCTION_ENHANCE: self._instruction_enhance,
            Step.ANALYSIS: self._analysis,
            Step.PLANNING: self._planning,
            Step.TASK_SPLIT: self._task_split,
            Step.EXECUTION_LOOP: self._execution_loop,
            Step.REVIEW: self._review,
        }
        handlers[step]()

    def _instruction_enhance(self) -> None:
        base_instruction = self.store.read_text("artifacts/instruction.md", default="Build requested system")
        enhanced = f"Enhanced instruction:\n{base_instruction}\n\nConstraint: orchestrator controls flow."
        self.store.write_text("artifacts/instruction.md", enhanced)

    def _analysis(self) -> None:
        instruction = self.store.read_text("artifacts/instruction.md")
        result = self.runtime.run_agent("analysis", {"instruction": instruction})
        self.store.write_text("artifacts/analysis.md", f"# Analysis\n\n{result['output']}\n")

    def _planning(self) -> None:
        analysis = self.store.read_text("artifacts/analysis.md")
        self.runtime.run_agent("planning", {"analysis": analysis})
        plan = {
            "goals": ["build workflow engine", "add execution loop", "add retry/human intervention"],
            "tasks": [
                {"id": "task_1", "title": "Scaffold orchestration modules", "complexity": "small"},
                {"id": "task_2", "title": "Implement execution loop", "complexity": "large"},
            ],
        }
        self.store.write_json("artifacts/plan.json", plan)

    def _task_split(self) -> None:
        plan = self.store.read_json("artifacts/plan.json", default={})
        queue = []
        for task in plan.get("tasks", []):
            queue.append({
                "id": task["id"],
                "title": task["title"],
                "description": task["title"],
                "complexity": task.get("complexity", "small"),
                "retries": 0,
                "status": "pending",
            })
        self.store.write_json("tasks/task_queue.json", queue)

    def _execution_loop(self) -> None:
        queue = self.store.read_json("tasks/task_queue.json", default=[])
        error_history: list[str] = []

        for task in queue:
            if task["status"] == "done":
                continue
            while task["status"] != "done":
                context = self.context_engine.build(task, repo_root=self.repo_root)
                executor = self.executors.choose_executor(task)
                runtime_meta = self.runtime.run_agent(
                    "execution_loop",
                    {"task": task, "context_summary": {"files": len(context.get("repo_files", []))}},
                    task=task,
                    executor_name=executor.name,
                )
                task["selected_model"] = runtime_meta["model"]
                task["selected_executor"] = executor.name
                patch = executor.run(task, context)
                self.store.write_text(f"patches/{task['id']}.patch", patch)

                result = self._run_tests(task)
                if result["ok"]:
                    task["status"] = "done"
                    self.memory.record_episode(task["id"], {"task": task, "result": "success"})
                else:
                    task["retries"] += 1
                    error_history.append(result["output"])
                    analysis = self.failures.analyze(result["output"], error_history)
                    self.memory.record_lesson(analysis.root_cause, analysis.fix_suggestion)
                    decision = self.retries.decide(task["retries"])
                    if decision.action == "abort":
                        task["status"] = "aborted"
                        break
                    if decision.action == "human_hint" and self.human.should_trigger(
                        same_error_count=error_history.count(result["output"]),
                        same_file_edit_count=task["retries"],
                        identical_stacktrace=analysis.stuck,
                    ):
                        msg = self.human.build_message(result["output"], ["retry", "reflection", "request hint"])
                        self.store.write_text("reports/human_intervention.md", msg)
                        task["status"] = "blocked"
                        break
            self.store.write_json("tasks/task_queue.json", queue)

    def _run_tests(self, task: dict) -> dict:
        if "fail" in task["title"].lower():
            return {"ok": False, "output": "FAIL: simulated failing task"}
        return {"ok": True, "output": "PASS"}

    def _review(self) -> None:
        queue = self.store.read_json("tasks/task_queue.json", default=[])
        done = sum(1 for t in queue if t.get("status") == "done")
        total = len(queue)
        self.store.write_text("reports/review.md", f"# Review\n\nCompleted {done}/{total} tasks.\n")
        self.store.write_text("reports/test_report.md", "All simulated checks complete.\n")

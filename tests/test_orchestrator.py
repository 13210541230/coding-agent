from __future__ import annotations

import json
from pathlib import Path

from agent_platform.orchestrator import Orchestrator


def test_full_workflow_generates_artifacts(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("print('hi')\n", encoding="utf-8")

    orch = Orchestrator(workspace=workspace, repo_root=repo)
    orch.run("full_dev", resume=False)

    assert (workspace / "artifacts" / "analysis.md").exists()
    assert (workspace / "artifacts" / "plan.json").exists()
    assert (workspace / "tasks" / "task_queue.json").exists()
    assert (workspace / "reports" / "review.md").exists()


def test_resume_from_saved_state(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("x=1\n", encoding="utf-8")

    orch = Orchestrator(workspace=workspace, repo_root=repo)
    orch.store.write_json(
        "state/workflow_state.json",
        {"workflow": "planning_only", "current_step": "planning", "completed": ["analysis"]},
    )
    orch.store.write_text("artifacts/analysis.md", "existing analysis")

    orch.run("planning_only", resume=True)

    plan = orch.store.read_json("artifacts/plan.json", default={})
    assert "tasks" in plan


def test_retry_to_abort_path(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("x=2\n", encoding="utf-8")

    orch = Orchestrator(workspace=workspace, repo_root=repo)
    queue = [
        {
            "id": "task_fail",
            "title": "fail this task",
            "description": "will fail",
            "complexity": "small",
            "retries": 4,
            "status": "pending",
        }
    ]
    orch.store.write_json("tasks/task_queue.json", queue)
    orch._execution_loop()

    persisted = json.loads((workspace / "tasks" / "task_queue.json").read_text(encoding="utf-8"))
    assert persisted[0]["status"] in {"aborted", "blocked"}

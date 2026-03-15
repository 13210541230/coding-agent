from __future__ import annotations

from pathlib import Path

from agent_platform.orchestrator import Orchestrator


def test_fixed_executor_can_force_claude_code(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("print('hi')\n", encoding="utf-8")

    orch = Orchestrator(
        workspace=workspace,
        repo_root=repo,
        config={"default_executor": "claude_code", "executor_routing_mode": "fixed"},
    )
    orch.store.write_json(
        "tasks/task_queue.json",
        [
            {
                "id": "task_x",
                "title": "small task",
                "description": "small task",
                "complexity": "small",
                "retries": 0,
                "status": "pending",
            }
        ],
    )

    orch._execution_loop()
    queue = orch.store.read_json("tasks/task_queue.json", default=[])
    assert queue[0]["selected_executor"] == "claude_code"


def test_task_level_model_override_and_low_cost_defaults(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("print('hi')\n", encoding="utf-8")

    orch = Orchestrator(
        workspace=workspace,
        repo_root=repo,
        config={"budget_mode": "low_cost", "default_executor": "codex", "executor_routing_mode": "fixed"},
    )
    orch.store.write_json(
        "tasks/task_queue.json",
        [
            {
                "id": "task_model_custom",
                "title": "small custom model",
                "description": "small custom model",
                "complexity": "small",
                "model": "custom-model-a",
                "retries": 0,
                "status": "pending",
            },
            {
                "id": "task_model_low_cost",
                "title": "small low cost model",
                "description": "small low cost model",
                "complexity": "small",
                "retries": 0,
                "status": "pending",
            },
        ],
    )

    orch._execution_loop()
    queue = orch.store.read_json("tasks/task_queue.json", default=[])

    assert queue[0]["selected_model"] == "custom-model-a"
    # complexity=small maps to nano (lowest cost) even under balanced/low_cost modes
    assert queue[1]["selected_model"] == "gpt-4.1-nano"

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from agent_platform.artifact_store import ArtifactStore
from agent_platform.cli import run_task


def test_run_task_writes_patch_artifact(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    repo = tmp_path / "repo"
    repo.mkdir()
    context_file = tmp_path / "context.json"
    context_file.write_text(json.dumps({"message": "hello world"}), encoding="utf-8")

    patch_path = run_task(
        workspace=workspace,
        repo_root=repo,
        task_id="hello_world",
        title="Create hello world patch",
        description="Generate a hello world patch artifact",
        complexity="small",
        context_file=context_file,
        output_name=None,
        default_executor="codex",
        executor_routing_mode="fixed",
        live_cli_execution=False,
        codex_path=None,
        claude_path=None,
    )

    assert patch_path == workspace / "patches" / "hello_world.patch"
    assert patch_path.exists()
    assert "Create hello world patch" in patch_path.read_text(encoding="utf-8")


def test_run_task_live_cli_mode_uses_executor_output(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    repo = tmp_path / "repo"
    repo.mkdir()

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, stdout="hello world patch\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    patch_path = run_task(
        workspace=workspace,
        repo_root=repo,
        task_id="hello_world_live",
        title="Create hello world patch in real CLI mode",
        description="Use the real CLI code path",
        complexity="small",
        context_file=None,
        output_name="hello_world_live",
        default_executor="codex",
        executor_routing_mode="fixed",
        live_cli_execution=True,
        codex_path="mycodex",
        claude_path=None,
    )

    assert patch_path.exists()
    assert patch_path.read_text(encoding="utf-8") == "hello world patch\n"


def test_disable_executor_writes_to_config(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    store = ArtifactStore(workspace)
    store.ensure_layout()
    store.write_json("artifacts/executor_config.json", {
        "executor_priority": ["mycodex", "claude_code", "codex"],
        "executor_disabled": {"mycodex": False, "claude_code": False, "codex": False},
    })

    from agent_platform.cli import disable_executor
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

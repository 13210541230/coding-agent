from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_platform.artifact_store import ArtifactStore
from agent_platform.executor_layer import ExecutorRouterV2
from agent_platform.orchestrator import Orchestrator
from agent_platform.types import WORKFLOWS


def init_workspace(workspace: Path) -> None:
    store = ArtifactStore(workspace)
    store.ensure_layout()
    if not (workspace / "artifacts" / "instruction.md").exists():
        store.write_text("artifacts/instruction.md", "Implement user requested system")
    if not (workspace / "artifacts" / "executor_config.json").exists():
        store.write_json(
            "artifacts/executor_config.json",
            {
                "executor_priority": ["mycodex", "claude_code", "codex"],
                "executor_disabled": {"mycodex": False, "claude_code": False, "codex": False},
                "executor_paths": {"mycodex": "mycodex", "claude_code": "claude", "codex": "codex"},
                "live_cli_execution": False,
                "stage_models": {
                    "analysis":       {"small": "gpt-5.2-codex", "medium": "gpt-5.4", "large": "gpt-5.4"},
                    "planning":       {"default": "gpt-5.4"},
                    "execution_loop": {"small": "gpt-5.1-codex-mini", "medium": "gpt-5.2-codex", "large": "gpt-5.4"},
                    "review":         {"default": "gpt-5.2-codex"},
                },
                "model_catalog": [],
                "budget_mode": "balanced",
            },
        )
    print(f"Workspace initialized: {workspace}")


def run_workflow(
    workspace: Path,
    workflow: str,
    resume: bool,
    repo_root: Path,
    config_file: Path | None,
    default_executor: str | None,
    budget_mode: str | None,
    executor_routing_mode: str | None,
    live_cli_execution: bool | None,
    codex_path: str | None,
    claude_path: str | None,
) -> None:
    config: dict = {}
    if config_file:
        config = json.loads(config_file.read_text(encoding="utf-8"))
    if default_executor:
        config["default_executor"] = default_executor
    if budget_mode:
        config["budget_mode"] = budget_mode
    if executor_routing_mode:
        config["executor_routing_mode"] = executor_routing_mode
    if live_cli_execution is not None:
        config["live_cli_execution"] = live_cli_execution
    if codex_path:
        config["codex_path"] = codex_path
    if claude_path:
        config["claude_path"] = claude_path

    orchestrator = Orchestrator(workspace=workspace, repo_root=repo_root, config=config)
    orchestrator.run(workflow=workflow, resume=resume)
    print(f"Workflow finished: {workflow}")


def run_task(
    workspace: Path,
    repo_root: Path,
    task_id: str,
    title: str,
    description: str,
    complexity: str,
    context_file: Path | None,
    output_name: str | None,
    default_executor: str,
    executor_routing_mode: str,
    live_cli_execution: bool,
    codex_path: str | None,
    claude_path: str | None,
) -> Path:
    store = ArtifactStore(workspace)
    store.ensure_layout()

    context = {}
    if context_file:
        context = json.loads(context_file.read_text(encoding="utf-8"))

    task = {
        "id": task_id,
        "title": title,
        "description": description,
        "complexity": complexity,
    }
    executor = ExecutorRouterV2(
        workdir=repo_root,
        default_executor=default_executor,
        routing_mode=executor_routing_mode,
        live_execution=live_cli_execution,
        codex_path=codex_path or "mycodex",
        claude_path=claude_path or "mycodex",
    ).choose_executor(task)
    execution = executor.run(title, context)

    patch_name = output_name or task_id
    patch_path = workspace / "patches" / f"{patch_name}.patch"
    patch = execution.output or f"# patch for {task_id} by {executor.name}\n# {title}\n"

    store.write_text(f"patches/{patch_name}.patch", patch)
    store.write_json(
        f"tasks/{task_id}.json",
        {
            **task,
            "selected_executor": executor.name,
            "live_cli_execution": live_cli_execution,
            "patch_path": f"patches/{patch_name}.patch",
            "exit_code": execution.exit_code,
            "success": execution.success,
        },
    )
    print(f"Patch written: {patch_path}")
    return patch_path


def disable_executor(workspace: Path, name: str) -> None:
    store = ArtifactStore(workspace)
    cfg = store.read_json("artifacts/executor_config.json", default={})
    disabled = cfg.setdefault("executor_disabled", {})
    disabled[name] = True
    store.write_json("artifacts/executor_config.json", cfg)
    print(f"Executor '{name}' disabled.")


def enable_executor(workspace: Path, name: str) -> None:
    store = ArtifactStore(workspace)
    cfg = store.read_json("artifacts/executor_config.json", default={})
    disabled = cfg.setdefault("executor_disabled", {})
    disabled[name] = False
    store.write_json("artifacts/executor_config.json", cfg)
    print(f"Executor '{name}' enabled.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-platform", description="Code Agent Orchestration Platform CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-workspace", help="Initialize workspace directory")
    init_parser.add_argument("workspace", type=Path)

    run_parser = subparsers.add_parser("run", help="Run orchestration workflow")
    run_parser.add_argument("--workspace", type=Path, required=True)
    run_parser.add_argument("--workflow", type=str, default="full_dev", choices=sorted(WORKFLOWS.keys()))
    run_parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    run_parser.add_argument("--repo-root", type=Path, default=Path("."))
    run_parser.add_argument("--config-file", type=Path, default=None)
    run_parser.add_argument("--default-executor", choices=["codex", "claude_code"], default=None)
    run_parser.add_argument("--budget-mode", choices=["balanced", "low_cost"], default=None)
    run_parser.add_argument("--executor-routing-mode", choices=["complexity", "fixed"], default=None)
    run_parser.add_argument("--live-cli-execution", action=argparse.BooleanOptionalAction, default=None)
    run_parser.add_argument("--codex-path", type=str, default=None)
    run_parser.add_argument("--claude-path", type=str, default=None)

    run_task_parser = subparsers.add_parser("run-task", help="Run a single task and write a patch artifact")
    run_task_parser.add_argument("--workspace", type=Path, required=True)
    run_task_parser.add_argument("--repo-root", type=Path, default=Path("."))
    run_task_parser.add_argument("--task-id", type=str, required=True)
    run_task_parser.add_argument("--title", type=str, required=True)
    run_task_parser.add_argument("--description", type=str, default="")
    run_task_parser.add_argument("--complexity", choices=["small", "large"], default="small")
    run_task_parser.add_argument("--context-file", type=Path, default=None)
    run_task_parser.add_argument("--output-name", type=str, default=None)
    run_task_parser.add_argument("--default-executor", choices=["codex", "claude_code"], default="codex")
    run_task_parser.add_argument("--executor-routing-mode", choices=["complexity", "fixed"], default="fixed")
    run_task_parser.add_argument("--live-cli-execution", action=argparse.BooleanOptionalAction, default=False)
    run_task_parser.add_argument("--codex-path", type=str, default=None)
    run_task_parser.add_argument("--claude-path", type=str, default=None)

    disable_parser = subparsers.add_parser("disable-executor", help="Mark an executor as disabled")
    disable_parser.add_argument("--workspace", type=Path, required=True)
    disable_parser.add_argument("--name", type=str, required=True)

    enable_parser = subparsers.add_parser("enable-executor", help="Mark an executor as enabled")
    enable_parser.add_argument("--workspace", type=Path, required=True)
    enable_parser.add_argument("--name", type=str, required=True)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "init-workspace":
        init_workspace(args.workspace)
        return

    if args.command == "run":
        run_workflow(
            args.workspace,
            args.workflow,
            args.resume,
            args.repo_root,
            args.config_file,
            args.default_executor,
            args.budget_mode,
            args.executor_routing_mode,
            args.live_cli_execution,
            args.codex_path,
            args.claude_path,
        )
        return

    if args.command == "run-task":
        run_task(
            args.workspace,
            args.repo_root,
            args.task_id,
            args.title,
            args.description,
            args.complexity,
            args.context_file,
            args.output_name,
            args.default_executor,
            args.executor_routing_mode,
            args.live_cli_execution,
            args.codex_path,
            args.claude_path,
        )
        return

    if args.command == "disable-executor":
        disable_executor(args.workspace, args.name)
        return

    if args.command == "enable-executor":
        enable_executor(args.workspace, args.name)
        return

    parser.error("Unknown command")


if __name__ == "__main__":
    main()

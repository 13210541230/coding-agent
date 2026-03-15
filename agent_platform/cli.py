from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_platform.artifact_store import ArtifactStore
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
                "default_executor": "codex",
                "executor_routing_mode": "complexity",
                "budget_mode": "balanced",
                "stage_models": {},
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

    orchestrator = Orchestrator(workspace=workspace, repo_root=repo_root, config=config)
    orchestrator.run(workflow=workflow, resume=resume)
    print(f"Workflow finished: {workflow}")


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
        )
        return

    parser.error("Unknown command")


if __name__ == "__main__":
    main()

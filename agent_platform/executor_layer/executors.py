from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Executor(ABC):
    name: str

    @abstractmethod
    def run(self, task: dict[str, Any], context: dict[str, Any]) -> str:
        raise NotImplementedError


class CodexExecutor(Executor):
    name = "codex"

    def run(self, task: dict[str, Any], context: dict[str, Any]) -> str:
        return f"# patch for {task['id']} by codex\n# {task['title']}\n"


class ClaudeCodeExecutor(Executor):
    name = "claude_code"

    def run(self, task: dict[str, Any], context: dict[str, Any]) -> str:
        return f"# patch for {task['id']} by claude_code\n# {task['title']}\n"


class ExecutorRouter:
    def __init__(self, default_executor: str = "codex", routing_mode: str = "complexity") -> None:
        self.executors = {
            "codex": CodexExecutor(),
            "claude_code": ClaudeCodeExecutor(),
        }
        if default_executor not in self.executors:
            raise ValueError(f"Unsupported default executor: {default_executor}")
        self.default_executor = default_executor
        self.routing_mode = routing_mode

    def choose_executor(self, task: dict[str, Any]) -> Executor:
        forced = task.get("executor")
        if forced in self.executors:
            return self.executors[str(forced)]

        if self.routing_mode == "fixed":
            return self.executors[self.default_executor]

        if task.get("complexity") == "large":
            return self.executors["claude_code"]
        return self.executors[self.default_executor]

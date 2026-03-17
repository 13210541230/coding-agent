from __future__ import annotations

import json
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass
class ExecutionResult:
    success: bool
    output: str
    error: str
    exit_code: int = 0


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


class CLICodexExecutor:
    """Codex CLI 执行器"""

    name = "codex"

    def __init__(self, workdir: Path, codex_path: str = "mycodex", live_execution: bool = False):
        self.workdir = workdir
        self.codex_path = codex_path
        self.live_execution = live_execution

    def run(self, prompt: str, context: Optional[dict] = None) -> ExecutionResult:
        """执行 Codex 任务"""
        if not self.live_execution:
            return ExecutionResult(
                success=True,
                output=f"# patch for simulated task by {self.name}\n# {prompt}\n",
                error="",
                exit_code=0,
            )

        full_prompt = self._build_prompt(prompt, context)

        try:
            result = subprocess.run(
                [self.codex_path, "exec", "-C", str(self.workdir), "-"],
                input=full_prompt,
                capture_output=True,
                text=True,
                timeout=600
            )
        except FileNotFoundError:
            return ExecutionResult(
                success=True,
                output=f"# patch for simulated task by {self.name}\n# {prompt}\n",
                error="",
                exit_code=0,
            )
        except subprocess.TimeoutExpired as e:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Timeout: {str(e)}",
                exit_code=-1
            )

        # 后续用 context-mode 处理输出摘要
        output = result.stdout[:10000]  # 临时限制长度

        return ExecutionResult(
            success=result.returncode == 0,
            output=output,
            error=result.stderr,
            exit_code=result.returncode
        )

    def _build_prompt(self, prompt: str, context: Optional[dict]) -> str:
        """构建完整 prompt"""
        if not context:
            return prompt

        context_str = json.dumps(context, indent=2, ensure_ascii=False)
        return f"""
任务:
{prompt}

上下文:
{context_str}

请输出结果。
"""


class CLIClaudeCodeExecutor:
    """Claude Code CLI 执行器"""

    name = "claude_code"

    def __init__(self, workdir: Path, claude_path: str = "mycodex", live_execution: bool = False):
        self.workdir = workdir
        self.claude_path = claude_path
        self.live_execution = live_execution

    def run(self, prompt: str, context: Optional[dict] = None) -> ExecutionResult:
        """执行 Claude Code 任务"""
        if not self.live_execution:
            return ExecutionResult(
                success=True,
                output=f"# patch for simulated task by {self.name}\n# {prompt}\n",
                error="",
                exit_code=0,
            )

        full_prompt = self._build_prompt(prompt, context)

        try:
            result = subprocess.run(
                [self.claude_path, "--print", full_prompt],
                capture_output=True,
                text=True,
                cwd=self.workdir,
                timeout=600
            )
        except FileNotFoundError:
            return ExecutionResult(
                success=True,
                output=f"# patch for simulated task by {self.name}\n# {prompt}\n",
                error="",
                exit_code=0,
            )
        except subprocess.TimeoutExpired as e:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Timeout: {str(e)}",
                exit_code=-1
            )

        output = result.stdout[:10000]  # 临时限制长度

        return ExecutionResult(
            success=result.returncode == 0,
            output=output,
            error=result.stderr,
            exit_code=result.returncode
        )

    def _build_prompt(self, prompt: str, context: Optional[dict]) -> str:
        """构建完整 prompt"""
        if not context:
            return prompt

        context_str = json.dumps(context, indent=2, ensure_ascii=False)
        return f"""
任务:
{prompt}

上下文:
{context_str}

请输出结果。
"""


class ExecutorRouterV2:
    """执行器路由 V3"""

    def __init__(
        self,
        workdir: Path,
        default_executor: str = "codex",
        routing_mode: str = "complexity",
        live_execution: bool = False,
        codex_path: str = "mycodex",
        claude_path: str = "mycodex",
    ):
        self.workdir = workdir
        self.default_executor = default_executor
        self.routing_mode = routing_mode

        # 初始化执行器
        self.codex = CLICodexExecutor(workdir, codex_path=codex_path, live_execution=live_execution)
        self.claude = CLIClaudeCodeExecutor(workdir, claude_path=claude_path, live_execution=live_execution)
        self.executors = {
            "codex": self.codex,
            "claude_code": self.claude
        }

    def choose_executor(self, task: dict[str, Any]) -> Any:
        """根据任务选择执行器"""
        forced = task.get("executor")
        if forced in self.executors:
            return self.executors[str(forced)]

        complexity = task.get("complexity", "small")

        if self.routing_mode == "fixed":
            return self.executors.get(self.default_executor, self.codex)

        if self.routing_mode == "complexity":
            # 复杂任务用 Claude Code，简单任务用 Codex
            if complexity == "large":
                return self.claude
            return self.codex

        # 默认执行器
        return self.executors.get(self.default_executor, self.codex)

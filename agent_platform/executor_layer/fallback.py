from __future__ import annotations
from agent_platform.executor_layer.registry import ExecutorRegistry
from agent_platform.executor_layer.executors import ExecutionResult

_DISABLE_PATTERNS = (
    "login", "authenticate", "401", "unauthorized",
    "quota", "balance", "429", "rate limit",
)


class ExecutorUnavailableError(Exception):
    def __init__(self, failures: dict[str, str]) -> None:
        super().__init__(f"All executors failed: {failures}")
        self.failures = failures


class FallbackChain:
    def __init__(self, registry: ExecutorRegistry) -> None:
        self._registry = registry

    def run(self, prompt: str, context: dict | None = None, model: str = "") -> ExecutionResult:
        # model hint is reserved for future use; executors do not yet accept a model arg
        candidates = self._registry.ordered()
        if not candidates:
            raise ExecutorUnavailableError({})

        failures: dict[str, str] = {}
        ctx = context or {}

        for entry in candidates:
            try:
                result = entry.executor.run(prompt, ctx)
            except FileNotFoundError as e:
                self._registry.disable(entry.name)
                failures[entry.name] = str(e)
                continue
            except Exception as e:
                failures[entry.name] = str(e)
                continue

            if result.success:
                return result

            reason = result.error or ""
            if any(p in reason.lower() for p in _DISABLE_PATTERNS):
                self._registry.disable(entry.name)

            failures[entry.name] = reason or f"exit_code={result.exit_code}"

        raise ExecutorUnavailableError(failures)

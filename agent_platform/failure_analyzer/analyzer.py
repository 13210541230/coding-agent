from __future__ import annotations

from collections import Counter

from agent_platform.types import FailureAnalysis


class FailureAnalyzer:
    def analyze(self, error_output: str, history: list[str]) -> FailureAnalysis:
        counter = Counter(history + [error_output])
        repeated = counter[error_output] > 2
        root = "test_failure" if "FAIL" in error_output.upper() else "runtime_error"
        suggestion = "inspect failing tests and fix implementation"
        return FailureAnalysis(root_cause=root, fix_suggestion=suggestion, stuck=repeated)

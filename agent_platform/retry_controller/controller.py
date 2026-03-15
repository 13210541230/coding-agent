from __future__ import annotations

from agent_platform.types import RetryDecision


class RetryController:
    def decide(self, retries: int) -> RetryDecision:
        if retries < 3:
            return RetryDecision(action="retry", reason="direct agent fix")
        if retries == 3:
            return RetryDecision(action="reflection", reason="trigger reflection")
        if retries == 4:
            return RetryDecision(action="human_hint", reason="request human hint")
        return RetryDecision(action="abort", reason="retry budget exhausted")

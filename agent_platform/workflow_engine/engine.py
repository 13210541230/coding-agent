from __future__ import annotations

from agent_platform.types import Step, WORKFLOWS


class WorkflowEngine:
    def steps_for(self, workflow: str) -> list[Step]:
        if workflow not in WORKFLOWS:
            raise ValueError(f"Unknown workflow: {workflow}")
        return WORKFLOWS[workflow]

    def resume_index(self, workflow: str, current_step: str | None) -> int:
        steps = self.steps_for(workflow)
        if not current_step:
            return 0
        for i, step in enumerate(steps):
            if step.value == current_step:
                return i
        return 0

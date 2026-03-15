from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Step(str, Enum):
    INSTRUCTION_ENHANCE = "instruction_enhance"
    ANALYSIS = "analysis"
    PLANNING = "planning"
    TASK_SPLIT = "task_split"
    EXECUTION_LOOP = "execution_loop"
    REVIEW = "review"


WORKFLOWS: dict[str, list[Step]] = {
    "full_dev": [
        Step.INSTRUCTION_ENHANCE,
        Step.ANALYSIS,
        Step.PLANNING,
        Step.TASK_SPLIT,
        Step.EXECUTION_LOOP,
        Step.REVIEW,
    ],
    "planning_only": [Step.ANALYSIS, Step.PLANNING],
    "execution_only": [Step.EXECUTION_LOOP],
    "review_only": [Step.REVIEW],
}


@dataclass
class Task:
    id: str
    title: str
    description: str
    complexity: str = "small"
    retries: int = 0
    status: str = "pending"


@dataclass
class WorkflowState:
    workflow: str
    current_step: str
    completed: list[str] = field(default_factory=list)


@dataclass
class FailureAnalysis:
    root_cause: str
    fix_suggestion: str
    stuck: bool = False


@dataclass
class RetryDecision:
    action: str
    reason: str


Context = dict[str, Any]

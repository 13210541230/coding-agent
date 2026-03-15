from __future__ import annotations

from dataclasses import asdict

from agent_platform.artifact_store import ArtifactStore
from agent_platform.types import WorkflowState


class StateManager:
    FILE = "state/workflow_state.json"

    def __init__(self, store: ArtifactStore):
        self.store = store

    def load(self) -> WorkflowState | None:
        data = self.store.read_json(self.FILE, default=None)
        if not data:
            return None
        return WorkflowState(**data)

    def save(self, state: WorkflowState) -> None:
        self.store.write_json(self.FILE, asdict(state))

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ArtifactStore:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.artifacts = workspace / "artifacts"
        self.tasks = workspace / "tasks"
        self.patches = workspace / "patches"
        self.reports = workspace / "reports"
        self.memory = workspace / "memory"
        self.state = workspace / "state"

    def ensure_layout(self) -> None:
        for p in [
            self.workspace,
            self.artifacts,
            self.tasks,
            self.patches,
            self.reports,
            self.memory,
            self.memory / "episodes",
            self.state,
        ]:
            p.mkdir(parents=True, exist_ok=True)

    def write_text(self, relative: str, content: str) -> None:
        target = self.workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def read_text(self, relative: str, default: str = "") -> str:
        target = self.workspace / relative
        if not target.exists():
            return default
        return target.read_text(encoding="utf-8")

    def write_json(self, relative: str, payload: Any) -> None:
        target = self.workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def read_json(self, relative: str, default: Any) -> Any:
        target = self.workspace / relative
        if not target.exists():
            return default
        return json.loads(target.read_text(encoding="utf-8"))

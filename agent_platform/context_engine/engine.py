from __future__ import annotations

from pathlib import Path

from agent_platform.artifact_store import ArtifactStore
from agent_platform.memory_system import MemorySystem


class ContextEngine:
    def __init__(self, store: ArtifactStore, memory: MemorySystem, max_files: int = 6, max_lessons: int = 3, max_tokens: int = 8000):
        self.store = store
        self.memory = memory
        self.max_files = max_files
        self.max_lessons = max_lessons
        self.max_tokens = max_tokens

    def build(self, task: dict, repo_root: Path) -> dict:
        candidates = list(repo_root.glob("**/*.py"))[: self.max_files]
        files = [str(p.relative_to(repo_root)) for p in candidates]
        lessons = self.memory.retrieve_relevant_lessons(task, max_lessons=self.max_lessons)
        return {
            "task": task,
            "repo_files": files,
            "lessons": lessons,
            "artifacts": {
                "analysis": self.store.read_text("artifacts/analysis.md"),
                "plan": self.store.read_json("artifacts/plan.json", default={}),
            },
            "limits": {
                "max_files": self.max_files,
                "max_lessons": self.max_lessons,
                "max_tokens": self.max_tokens,
            },
        }

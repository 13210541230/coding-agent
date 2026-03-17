from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_platform.artifact_store import ArtifactStore


class MemorySystem:
    LESSONS_FILE = "memory/lessons.json"

    def __init__(self, store: ArtifactStore):
        self.store = store

    def retrieve_relevant_lessons(self, task: dict[str, Any], max_lessons: int = 3) -> list[dict[str, str]]:
        lessons = self.store.read_json(self.LESSONS_FILE, default=[])
        task_text = f"{task.get('title', '')} {task.get('description', '')}".lower()
        ranked = []
        for lesson in lessons:
            problem = lesson.get("problem", "").lower()
            score = sum(tok in task_text for tok in problem.split())
            ranked.append((score, lesson))
        ranked.sort(key=lambda x: x[0], reverse=True)
        return [lesson for _, lesson in ranked[:max_lessons]]

    def record_lesson(self, problem: str, solution: str) -> None:
        lessons = self.store.read_json(self.LESSONS_FILE, default=[])
        lessons.append({"problem": problem, "solution": solution})
        self.store.write_json(self.LESSONS_FILE, lessons)

    def record_episode(self, task_id: str, payload: dict[str, Any]) -> Path:
        path = self.store.workspace / "memory" / "episodes" / f"{task_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(__import__("json").dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

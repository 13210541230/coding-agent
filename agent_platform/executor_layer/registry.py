from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutorEntry:
    name: str
    executor: Any
    priority: int
    enabled: bool = True


class ExecutorRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, ExecutorEntry] = {}

    def register(self, entry: ExecutorEntry) -> None:
        self._entries[entry.name] = entry

    def disable(self, name: str) -> None:
        if name in self._entries:
            self._entries[name].enabled = False

    def enable(self, name: str) -> None:
        if name in self._entries:
            self._entries[name].enabled = True

    def ordered(self) -> list[ExecutorEntry]:
        return sorted(
            [e for e in self._entries.values() if e.enabled],
            key=lambda e: e.priority,
        )

    def get(self, name: str) -> ExecutorEntry | None:
        return self._entries.get(name)

    def all_disabled(self) -> bool:
        return len(self.ordered()) == 0

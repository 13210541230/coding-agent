# agent_platform/model_router/catalog.py
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelEntry:
    name: str
    executor: str
    tier: int
    context_window: int
    tags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not (1 <= self.tier <= 4):
            raise ValueError(f"tier must be 1–4, got {self.tier!r}")
        if not self.name:
            raise ValueError("name must not be empty")
        if not self.executor:
            raise ValueError("executor must not be empty")


class ModelCatalog:
    def __init__(self, entries: list[ModelEntry]) -> None:
        # user entries override built-ins with same (name, executor)
        seen: dict[tuple[str, str], ModelEntry] = {}
        for e in entries:
            seen[(e.name, e.executor)] = e
        self._entries = list(seen.values())

    def for_executor(self, executor: str) -> list[ModelEntry]:
        return sorted(
            [e for e in self._entries if e.executor == executor],
            key=lambda e: e.tier,
        )

    def best_for(self, executor: str, max_tier: int = 4) -> ModelEntry | None:
        candidates = [e for e in self.for_executor(executor) if e.tier <= max_tier]
        return candidates[0] if candidates else None

    def by_tier(self, tier: int) -> list[ModelEntry]:
        return [e for e in self._entries if e.tier == tier]

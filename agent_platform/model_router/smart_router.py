from __future__ import annotations
import re
from dataclasses import dataclass

# Bilingual signals: Chinese (zh) + English keywords for task classification.
# ASCII signals use word-boundary matching; CJK signals use substring matching.
LARGE_SIGNALS = [
    "重构", "架构", "设计", "refactor", "architect", "system", "migrate",
    "rewrite", "overhaul", "redesign", "split", "extract module",
]
SMALL_SIGNALS = [
    "修复", "fix", "typo", "rename", "add comment", "update doc",
    "bump", "format", "lint", "cleanup comment",
]
DESCRIPTION_LENGTH_LARGE = 500
DESCRIPTION_LENGTH_SMALL = 80


def _signal_match(sig: str, text: str) -> bool:
    """Match signal in text. ASCII signals use word boundaries to avoid false positives
    (e.g. 'fix' should not match 'prefix'); CJK signals use substring matching."""
    if sig.isascii():
        return bool(re.search(r"\b" + re.escape(sig) + r"\b", text))
    return sig in text


@dataclass
class AssessResult:
    complexity: str      # "small" | "medium" | "large"
    method: str          # "explicit" | "rule" | "default"
    confidence: float    # 0.0–1.0


class SmartRouter:
    def assess(self, task: dict) -> AssessResult:
        return _rule_assess(task)


def _rule_assess(task: dict) -> AssessResult:
    # 1. explicit field
    explicit = task.get("complexity")
    if explicit in {"small", "medium", "large"}:
        return AssessResult(explicit, method="explicit", confidence=1.0)

    title = (task.get("title") or "").lower()
    desc = (task.get("description") or "").lower()
    text = f"{title} {desc}"

    # 2. keyword signals
    if any(_signal_match(sig, text) for sig in LARGE_SIGNALS):
        return AssessResult("large", method="rule", confidence=0.8)
    if any(_signal_match(sig, text) for sig in SMALL_SIGNALS):
        return AssessResult("small", method="rule", confidence=0.8)

    # 3. length heuristic
    if len(desc) >= DESCRIPTION_LENGTH_LARGE:
        return AssessResult("large", method="rule", confidence=0.6)
    if len(desc) <= DESCRIPTION_LENGTH_SMALL:
        return AssessResult("small", method="rule", confidence=0.6)

    # 4. default
    return AssessResult("medium", method="default", confidence=0.5)

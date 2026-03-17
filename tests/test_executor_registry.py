from __future__ import annotations
import pytest
from agent_platform.executor_layer.registry import ExecutorEntry, ExecutorRegistry


class FakeExecutor:
    def __init__(self, name): self.name = name


def make_registry():
    r = ExecutorRegistry()
    r.register(ExecutorEntry("mycodex",    FakeExecutor("mycodex"),    priority=0))
    r.register(ExecutorEntry("claude_code",FakeExecutor("claude_code"),priority=1))
    r.register(ExecutorEntry("codex",      FakeExecutor("codex"),      priority=2))
    return r


def test_ordered_returns_all_enabled_sorted_by_priority():
    r = make_registry()
    names = [e.name for e in r.ordered()]
    assert names == ["mycodex", "claude_code", "codex"]


def test_disable_excludes_from_ordered():
    r = make_registry()
    r.disable("claude_code")
    names = [e.name for e in r.ordered()]
    assert "claude_code" not in names
    assert names == ["mycodex", "codex"]


def test_enable_restores_to_ordered():
    r = make_registry()
    r.disable("mycodex")
    r.enable("mycodex")
    assert r.ordered()[0].name == "mycodex"


def test_get_returns_entry_regardless_of_enabled():
    r = make_registry()
    r.disable("codex")
    assert r.get("codex") is not None
    assert r.get("codex").enabled is False


def test_get_unknown_returns_none():
    assert make_registry().get("nonexistent") is None


def test_all_disabled_false_by_default():
    assert make_registry().all_disabled() is False


def test_all_disabled_true_when_all_off():
    r = make_registry()
    for name in ("mycodex", "claude_code", "codex"):
        r.disable(name)
    assert r.all_disabled() is True


def test_all_disabled_false_on_empty_registry():
    assert ExecutorRegistry().all_disabled() is False


def test_disable_unknown_name_raises():
    with pytest.raises(KeyError):
        make_registry().disable("nonexistent")


def test_enable_unknown_name_raises():
    with pytest.raises(KeyError):
        make_registry().enable("nonexistent")

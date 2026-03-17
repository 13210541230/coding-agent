from __future__ import annotations
import pytest
from agent_platform.executor_layer.fallback import FallbackChain, ExecutorUnavailableError
from agent_platform.executor_layer.registry import ExecutorEntry, ExecutorRegistry
from agent_platform.executor_layer.executors import ExecutionResult


class SuccessExecutor:
    name = "success"
    def run(self, prompt, context=None): return ExecutionResult(True, "ok", "", 0)


class FailExecutor:
    name = "fail"
    def run(self, prompt, context=None): return ExecutionResult(False, "", "generic error", 1)


class LoginErrorExecutor:
    name = "login_fail"
    def run(self, prompt, context=None):
        return ExecutionResult(False, "", "Error: login required to continue", 1)


class QuotaErrorExecutor:
    name = "quota_fail"
    def run(self, prompt, context=None):
        return ExecutionResult(False, "", "429 quota exceeded balance", 1)


def make_registry(*executors):
    r = ExecutorRegistry()
    for i, exc in enumerate(executors):
        r.register(ExecutorEntry(exc.name, exc, priority=i))
    return r


def test_success_on_first_executor():
    r = make_registry(SuccessExecutor())
    result = FallbackChain(r).run("task", {})
    assert result.success is True
    assert result.output == "ok"


def test_falls_back_to_second_on_first_failure():
    r = make_registry(FailExecutor(), SuccessExecutor())
    result = FallbackChain(r).run("task", {})
    assert result.success is True


def test_login_error_auto_disables_executor():
    login = LoginErrorExecutor()
    r = make_registry(login, SuccessExecutor())
    FallbackChain(r).run("task", {})
    assert r.get("login_fail").enabled is False


def test_quota_error_auto_disables_executor():
    quota = QuotaErrorExecutor()
    r = make_registry(quota, SuccessExecutor())
    FallbackChain(r).run("task", {})
    assert r.get("quota_fail").enabled is False


def test_generic_failure_does_not_disable():
    fail = FailExecutor()
    r = make_registry(fail, SuccessExecutor())
    FallbackChain(r).run("task", {})
    assert r.get("fail").enabled is True


def test_all_fail_raises_executor_unavailable_error():
    r = make_registry(FailExecutor())
    with pytest.raises(ExecutorUnavailableError) as exc_info:
        FallbackChain(r).run("task", {})
    assert "fail" in exc_info.value.failures


def test_empty_registry_raises_executor_unavailable_error():
    r = ExecutorRegistry()
    with pytest.raises(ExecutorUnavailableError):
        FallbackChain(r).run("task", {})


def test_all_disabled_raises_executor_unavailable_error():
    r = make_registry(SuccessExecutor())
    r.disable("success")
    with pytest.raises(ExecutorUnavailableError):
        FallbackChain(r).run("task", {})

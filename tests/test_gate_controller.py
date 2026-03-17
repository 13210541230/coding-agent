
from __future__ import annotations

import json
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

import pytest

from agent_platform.artifact_store import ArtifactStore
from agent_platform.gate_controller import GateController


@pytest.fixture
def temp_workspace():
    """创建临时工作空间"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def artifact_store(temp_workspace):
    """创建 ArtifactStore 实例"""
    return ArtifactStore(temp_workspace)


@pytest.fixture
def gate_controller(artifact_store):
    """创建 GateController 实例"""
    return GateController(artifact_store)


class TestGateTypes:
    """测试门控类型"""

    def test_auto_gate(self, gate_controller):
        """测试自动门控"""
        assert gate_controller.can_proceed("analysis", GateController.GATE_AUTO) is True

    def test_manual_gate_not_approved(self, gate_controller):
        """测试未批准的手动门控"""
        assert gate_controller.can_proceed("planning", GateController.GATE_MANUAL) is False

    def test_manual_gate_approved(self, gate_controller, artifact_store, temp_workspace):
        """测试已批准的手动门控"""
        approved_path = temp_workspace / "gates/planning_approved.json"
        approved_path.parent.mkdir(parents=True, exist_ok=True)
        approved_path.write_text(json.dumps({"approved": True}))

        assert gate_controller.can_proceed("planning", GateController.GATE_MANUAL) is True

    def test_on_blocked_gate(self, gate_controller):
        """测试阻塞时触发的门控"""
        assert gate_controller.can_proceed("execution_loop", GateController.GATE_ON_BLOCKED) is True


class TestApproval:
    """测试审批功能"""

    def test_approve_phase(self, gate_controller, temp_workspace):
        """测试批准阶段"""
        gate_controller.approve_phase("planning", "user1")

        approved_path = temp_workspace / "gates/planning_approved.json"
        assert approved_path.exists()

        data = json.loads(approved_path.read_text())
        assert data["approved"] is True
        assert data["approver"] == "user1"

    def test_reject_phase(self, gate_controller, temp_workspace):
        """测试拒绝阶段"""
        gate_controller.reject_phase("planning", "Reason for rejection", "user1")

        approved_path = temp_workspace / "gates/planning_approved.json"
        assert approved_path.exists()

        data = json.loads(approved_path.read_text())
        assert data["approved"] is False
        assert data["reason"] == "Reason for rejection"
        assert data["approver"] == "user1"

    def test_can_proceed_after_approve(self, gate_controller):
        """测试批准后可以继续"""
        gate_controller.approve_phase("planning")
        assert gate_controller.can_proceed("planning", GateController.GATE_MANUAL) is True


class TestWaitForApproval:
    """测试等待审批功能"""

    def test_wait_for_approval_timeout(self, gate_controller):
        """测试审批超时"""
        # 不写入审批，等待 1 秒超时
        result = gate_controller.wait_for_approval("planning", timeout=1)
        assert result is False

    def test_wait_for_approval_success(self, gate_controller, temp_workspace):
        """测试审批成功"""
        # 在后台线程中 0.5 秒后写入审批
        def approve_later():
            time.sleep(0.5)
            gate_controller.approve_phase("planning")

        thread = threading.Thread(target=approve_later)
        thread.start()

        # 等待审批，超时 5 秒
        result = gate_controller.wait_for_approval("planning", timeout=5)
        assert result is True


class TestIntervention:
    """测试人工介入功能"""

    def test_request_intervention(self, gate_controller, temp_workspace):
        """测试请求人工介入"""
        gate_controller.request_intervention(
            task_id="task_001",
            error="Test error",
            context={"task": "test task"}
        )

        pending_path = temp_workspace / "gates/intervention_pending.json"
        assert pending_path.exists()

        data = json.loads(pending_path.read_text())
        assert data["task_id"] == "task_001"
        assert data["error"] == "Test error"

    def test_wait_for_intervention_timeout(self, gate_controller):
        """测试介入超时"""
        result = gate_controller.wait_for_intervention(timeout=1)
        assert result is False

    def test_wait_for_intervention_success(self, gate_controller, temp_workspace):
        """测试介入成功"""
        def resolve_later():
            time.sleep(0.5)
            resolved_path = temp_workspace / "gates/intervention_resolved.json"
            resolved_path.write_text(json.dumps({"resolved": True}))

        thread = threading.Thread(target=resolve_later)
        thread.start()

        result = gate_controller.wait_for_intervention(timeout=5)
        assert result is True


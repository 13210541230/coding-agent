from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from agent_platform.state_manager import StateManagerV2
from agent_platform.types import Checkpoint, Summary, TaskState, WorkflowStateV2


@pytest.fixture
def temp_workspace():
    """创建临时工作空间"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def state_manager(temp_workspace):
    """创建 StateManagerV2 实例"""
    return StateManagerV2(temp_workspace)


class TestWorkflowState:
    """测试工作流状态读写"""

    def test_save_and_load_workflow_state(self, state_manager):
        """测试保存和加载工作流状态"""
        state = WorkflowStateV2(
            workflow="full_dev",
            current_phase="planning",
            completed=["instruction_enhance", "analysis"],
        )

        state_manager.save_workflow_state(state)
        loaded = state_manager.load_workflow_state()

        assert loaded is not None
        assert loaded.workflow == "full_dev"
        assert loaded.current_phase == "planning"
        assert loaded.completed == ["instruction_enhance", "analysis"]

    def test_load_workflow_state_nonexistent(self, state_manager):
        """测试加载不存在的状态"""
        loaded = state_manager.load_workflow_state()
        assert loaded is None


class TestArtifacts:
    """测试阶段产出读写"""

    def test_save_and_load_artifact(self, state_manager):
        """测试保存和加载阶段产出"""
        phase = "planning"
        key = "plan"
        value = {"tasks": [{"id": "1", "title": "Task 1"}], "dependencies": []}

        state_manager.save_artifact(phase, key, value)
        loaded = state_manager.load_artifact(phase, key)

        assert loaded == value

    def test_load_artifact_nonexistent(self, state_manager):
        """测试加载不存在的产出"""
        loaded = state_manager.load_artifact("planning", "nonexistent")
        assert loaded is None


class TestCheckpoints:
    """测试检查点读写"""

    def test_save_and_load_checkpoint(self, state_manager):
        """测试保存和加载检查点"""
        phase = "execution_loop"
        checkpoint = Checkpoint(
            phase=phase,
            result={"status": "completed", "task_count": 5},
            duration_ms=15000,
        )

        state_manager.save_checkpoint(phase, checkpoint)
        loaded = state_manager.load_checkpoint(phase)

        assert loaded is not None
        assert loaded.phase == phase
        assert loaded.result == {"status": "completed", "task_count": 5}
        assert loaded.duration_ms == 15000

    def test_load_checkpoint_nonexistent(self, state_manager):
        """测试加载不存在的检查点"""
        loaded = state_manager.load_checkpoint("nonexistent")
        assert loaded is None


class TestSummary:
    """测试摘要读写"""

    def test_save_and_load_summary(self, state_manager):
        """测试保存和加载摘要"""
        summary = Summary(
            current_phase="planning",
            last_result={"tasks_created": 10},
            next_phase="execution_loop",
            completed=False,
        )

        state_manager.save_summary(summary)
        loaded = state_manager.load_summary()

        assert loaded is not None
        assert loaded.current_phase == "planning"
        assert loaded.last_result == {"tasks_created": 10}
        assert loaded.next_phase == "execution_loop"
        assert loaded.completed is False

    def test_load_summary_nonexistent(self, state_manager):
        """测试加载不存在的摘要"""
        loaded = state_manager.load_summary()
        assert loaded is None


class TestTaskState:
    """测试子任务状态读写"""

    def test_save_and_load_task_state(self, state_manager):
        """测试保存和加载子任务状态"""
        task_id = "task_001"
        state = TaskState(
            id=task_id,
            title="Implement feature X",
            status="in_progress",
            retries=1,
            result={"output": "Some output"},
        )

        state_manager.save_task_state(task_id, state)
        loaded = state_manager.load_task_state(task_id)

        assert loaded is not None
        assert loaded.id == task_id
        assert loaded.title == "Implement feature X"
        assert loaded.status == "in_progress"
        assert loaded.retries == 1

    def test_load_task_state_nonexistent(self, state_manager):
        """测试加载不存在的任务状态"""
        loaded = state_manager.load_task_state("nonexistent")
        assert loaded is None


class TestGateApproval:
    """测试门控审批"""

    def test_save_and_check_approval(self, state_manager):
        """测试保存和检查审批状态"""
        gate_name = "planning_approval"

        # 初始状态应为未批准
        assert state_manager.is_gate_approved(gate_name) is False

        # 批准
        state_manager.save_gate_approval(gate_name, approved=True, approver="user1")
        assert state_manager.is_gate_approved(gate_name) is True

        # 拒绝
        state_manager.save_gate_approval(gate_name, approved=False, approver="user1")
        assert state_manager.is_gate_approved(gate_name) is False

    def test_is_gate_approved_nonexistent(self, state_manager):
        """测试检查不存在的门控"""
        assert state_manager.is_gate_approved("nonexistent_gate") is False


class TestResume:
    """测试恢复功能"""

    def test_load_for_resume_empty(self, state_manager):
        """测试空状态下的恢复"""
        resume_data = state_manager.load_for_resume()

        assert resume_data["workflow_state"] is None
        assert resume_data["summary"] is None
        assert resume_data["checkpoints"] == {}
        assert resume_data["task_states"] == {}
        assert resume_data["gate_approvals"] == {}

    def test_load_for_resume_with_data(self, state_manager):
        """测试有数据时的恢复"""
        # 保存一些数据
        workflow_state = WorkflowStateV2(
            workflow="full_dev",
            current_phase="execution_loop",
            completed=["instruction_enhance", "analysis", "planning"],
        )
        state_manager.save_workflow_state(workflow_state)

        summary = Summary(
            current_phase="execution_loop",
            last_result={"completed_tasks": 3},
            next_phase="review",
            completed=False,
        )
        state_manager.save_summary(summary)

        checkpoint = Checkpoint(
            phase="planning",
            result={"plan": "completed"},
            duration_ms=5000,
        )
        state_manager.save_checkpoint("planning", checkpoint)

        task_state = TaskState(
            id="task_001",
            title="Task 1",
            status="completed",
            retries=0,
        )
        state_manager.save_task_state("task_001", task_state)

        state_manager.save_gate_approval("planning", approved=True)

        # 恢复数据
        resume_data = state_manager.load_for_resume()

        assert resume_data["workflow_state"] is not None
        assert resume_data["workflow_state"].current_phase == "execution_loop"

        assert resume_data["summary"] is not None
        assert resume_data["summary"].current_phase == "execution_loop"

        assert "planning" in resume_data["checkpoints"]
        assert resume_data["checkpoints"]["planning"].result == {"plan": "completed"}

        assert "task_001" in resume_data["task_states"]
        assert resume_data["task_states"]["task_001"].title == "Task 1"

        assert resume_data["gate_approvals"]["planning"]["approved"] is True


class TestDatetimeHandling:
    """测试日期时间处理"""

    def test_datetime_persistence(self, state_manager):
        """测试日期时间持久化"""
        before = datetime.now()

        state = WorkflowStateV2(
            workflow="test",
            current_phase="phase1",
            completed=[],
        )

        state_manager.save_workflow_state(state)
        loaded = state_manager.load_workflow_state()

        after = datetime.now()

        assert loaded is not None
        assert loaded.created_at >= before
        assert loaded.created_at <= after
        assert loaded.updated_at >= before
        assert loaded.updated_at <= after
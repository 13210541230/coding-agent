from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from agent_platform.artifact_store import ArtifactStore
from agent_platform.types import Checkpoint, Summary, TaskState, WorkflowState, WorkflowStateV2


class StateManagerV2:
    """State Manager V2 - 支持步骤内恢复的细粒度状态管理"""

    # 文件路径常量
    WORKFLOW_STATE_FILE = "state/workflow_state.json"
    ARTIFACTS_DIR = "artifacts"
    CHECKPOINTS_DIR = "state/checkpoints"
    SUMMARY_FILE = "state/summary.json"
    TASKS_DIR = "state/tasks"
    GATE_APPROVALS_FILE = "state/gate_approvals.json"

    def __init__(self, workspace: Path):
        """初始化 StateManagerV2

        Args:
            workspace: 工作空间根目录
        """
        self.workspace = workspace
        self.store = ArtifactStore(workspace)
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """确保必要的目录结构存在"""
        self.store.ensure_layout()
        (self.workspace / self.CHECKPOINTS_DIR).mkdir(parents=True, exist_ok=True)
        (self.workspace / self.TASKS_DIR).mkdir(parents=True, exist_ok=True)
        (self.workspace / self.ARTIFACTS_DIR).mkdir(parents=True, exist_ok=True)

    # ========== Workflow State ==========

    def save_workflow_state(self, state: WorkflowStateV2) -> None:
        """保存工作流状态

        Args:
            state: 工作流状态对象
        """
        data = asdict(state)
        data["created_at"] = state.created_at.isoformat()
        data["updated_at"] = state.updated_at.isoformat()
        self.store.write_json(self.WORKFLOW_STATE_FILE, data)

    def load_workflow_state(self) -> WorkflowStateV2 | None:
        """加载工作流状态

        Returns:
            工作流状态对象，如果不存在则返回 None
        """
        data = self.store.read_json(self.WORKFLOW_STATE_FILE, None)
        if not data:
            return None

        if "current_phase" not in data and "current_step" in data:
            data["current_phase"] = data.pop("current_step")
        if "created_at" not in data:
            data["created_at"] = datetime.now()
        if "updated_at" not in data:
            data["updated_at"] = datetime.now()

        # 转换 datetime 字符串
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data and isinstance(data["updated_at"], str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])

        return WorkflowStateV2(**data)

    # ========== Artifacts ==========

    def save_artifact(self, phase: str, key: str, value: Any) -> None:
        """保存阶段产出

        Args:
            phase: 阶段名称
            key: 产出键名
            value: 产出值
        """
        artifact_file = f"{self.ARTIFACTS_DIR}/{phase}/{key}.json"
        self.store.write_json(artifact_file, value)

    def load_artifact(self, phase: str, key: str) -> Any:
        """加载阶段产出

        Args:
            phase: 阶段名称
            key: 产出键名

        Returns:
            产出值，如果不存在则返回 None
        """
        artifact_file = f"{self.ARTIFACTS_DIR}/{phase}/{key}.json"
        return self.store.read_json(artifact_file, None)

    # ========== Checkpoints ==========

    def save_checkpoint(self, phase: str, checkpoint: Checkpoint) -> None:
        """保存检查点

        Args:
            phase: 阶段名称
            checkpoint: 检查点对象
        """
        checkpoint_file = f"{self.CHECKPOINTS_DIR}/{phase}.json"
        data = asdict(checkpoint)
        data["timestamp"] = checkpoint.timestamp.isoformat()
        self.store.write_json(checkpoint_file, data)

    def load_checkpoint(self, phase: str) -> Checkpoint | None:
        """加载检查点

        Args:
            phase: 阶段名称

        Returns:
            检查点对象，如果不存在则返回 None
        """
        checkpoint_file = f"{self.CHECKPOINTS_DIR}/{phase}.json"
        data = self.store.read_json(checkpoint_file, None)
        if not data:
            return None

        # 转换 datetime 字符串
        if "timestamp" in data and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])

        return Checkpoint(**data)

    # ========== Summary ==========

    def save_summary(self, summary: Summary) -> None:
        """保存摘要

        Args:
            summary: 摘要对象
        """
        data = asdict(summary)
        data["timestamp"] = summary.timestamp.isoformat()
        self.store.write_json(self.SUMMARY_FILE, data)

    def load_summary(self) -> Summary | None:
        """加载摘要

        Returns:
            摘要对象，如果不存在则返回 None
        """
        data = self.store.read_json(self.SUMMARY_FILE, None)
        if not data:
            return None

        # 转换 datetime 字符串
        if "timestamp" in data and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])

        return Summary(**data)

    # ========== Task State ==========

    def save_task_state(self, task_id: str, state: TaskState) -> None:
        """保存子任务状态

        Args:
            task_id: 任务 ID
            state: 任务状态对象
        """
        task_file = f"{self.TASKS_DIR}/{task_id}.json"
        data = asdict(state)
        data["created_at"] = state.created_at.isoformat()
        data["updated_at"] = state.updated_at.isoformat()
        self.store.write_json(task_file, data)

    def load_task_state(self, task_id: str) -> TaskState | None:
        """加载子任务状态

        Args:
            task_id: 任务 ID

        Returns:
            任务状态对象，如果不存在则返回 None
        """
        task_file = f"{self.TASKS_DIR}/{task_id}.json"
        data = self.store.read_json(task_file, None)
        if not data:
            return None

        # 转换 datetime 字符串
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data and isinstance(data["updated_at"], str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])

        return TaskState(**data)

    # ========== Gate Approval ==========

    def save_gate_approval(self, gate_name: str, approved: bool, approver: str = "system") -> None:
        """保存门控审批结果

        Args:
            gate_name: 门控名称
            approved: 是否已批准
            approver: 审批人
        """
        approvals = self.store.read_json(self.GATE_APPROVALS_FILE, {})
        approvals[gate_name] = {
            "approved": approved,
            "approver": approver,
            "timestamp": datetime.now().isoformat(),
        }
        self.store.write_json(self.GATE_APPROVALS_FILE, approvals)

    def is_gate_approved(self, gate_name: str) -> bool:
        """检查门控是否已批准

        Args:
            gate_name: 门控名称

        Returns:
            如果门控已批准返回 True，否则返回 False
        """
        approvals = self.store.read_json(self.GATE_APPROVALS_FILE, {})
        gate = approvals.get(gate_name, {})
        return gate.get("approved", False)

    # ========== Resume ==========

    def load_for_resume(self) -> dict[str, Any]:
        """恢复时加载所有必要信息

        Returns:
            包含所有恢复所需信息的字典:
            - workflow_state: 工作流状态
            - summary: 当前摘要
            - checkpoints: 所有检查点
            - task_states: 所有任务状态
            - gate_approvals: 门控审批状态
        """
        result = {
            "workflow_state": self.load_workflow_state(),
            "summary": self.load_summary(),
            "checkpoints": {},
            "task_states": {},
            "gate_approvals": self.store.read_json(self.GATE_APPROVALS_FILE, {}),
        }

        # 加载所有检查点
        checkpoints_dir = self.workspace / self.CHECKPOINTS_DIR
        if checkpoints_dir.exists():
            for checkpoint_file in checkpoints_dir.glob("*.json"):
                phase = checkpoint_file.stem
                result["checkpoints"][phase] = self.load_checkpoint(phase)

        # 加载所有任务状态
        tasks_dir = self.workspace / self.TASKS_DIR
        if tasks_dir.exists():
            for task_file in tasks_dir.glob("*.json"):
                task_id = task_file.stem
                result["task_states"][task_id] = self.load_task_state(task_id)

        return result


class StateManager(StateManagerV2):
    """Backward-compatible wrapper for the legacy workflow state API."""

    def __init__(self, store: ArtifactStore):
        super().__init__(store.workspace)

    def save(self, state: WorkflowState) -> None:
        current = self.load_workflow_state()
        created_at = current.created_at if current else datetime.now()
        self.save_workflow_state(
            WorkflowStateV2(
                workflow=state.workflow,
                current_phase=state.current_step,
                completed=list(state.completed),
                created_at=created_at,
                updated_at=datetime.now(),
            )
        )

    def load(self) -> WorkflowState | None:
        state = self.load_workflow_state()
        if state is None:
            return None
        return WorkflowState(
            workflow=state.workflow,
            current_step=state.current_phase,
            completed=list(state.completed),
        )

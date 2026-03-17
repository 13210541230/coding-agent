
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any

from agent_platform.artifact_store import ArtifactStore


class GateController:
    """程序化门控控制器 - V3 实现"""

    # 门控类型
    GATE_AUTO = "auto"
    GATE_MANUAL = "manual"
    GATE_ON_BLOCKED = "on_blocked"

    # 目录和文件路径常量
    GATES_DIR = "gates"

    def __init__(self, store: ArtifactStore):
        """初始化 GateController

        Args:
            store: ArtifactStore 实例
        """
        self.store = store
        self._ensure_gates_dir()

    def _ensure_gates_dir(self) -> None:
        """确保 gates 目录存在"""
        gates_path = Path(self.store.workspace) / self.GATES_DIR
        gates_path.mkdir(parents=True, exist_ok=True)

    def can_proceed(self, phase: str, gate_type: str) -> bool:
        """检查是否可以进入下一阶段

        Args:
            phase: 阶段名称
            gate_type: 门控类型

        Returns:
            如果可以进入下一阶段返回 True，否则返回 False
        """
        if gate_type == self.GATE_AUTO:
            return True

        if gate_type == self.GATE_MANUAL:
            # 读取门控确认文件
            approved_path = self._approved_path(phase)
            if not approved_path.exists():
                return False

            data = self.store.read_json(str(approved_path), default={})
            return data.get("approved", False)

        if gate_type == self.GATE_ON_BLOCKED:
            # 默认允许，阻塞时会触发介入
            return True

        return True

    def request_approval(self, phase: str, content: dict[str, Any]) -> None:
        """请求人工确认

        Args:
            phase: 阶段名称
            content: 待确认内容
        """
        # 写入待确认内容
        pending_path = self._pending_path(phase)
        content["timestamp"] = datetime.now().isoformat()
        content["phase"] = phase
        self.store.write_json(str(pending_path), content)

        # 打印提示
        self._print_approval_prompt(phase, content)

    def wait_for_approval(self, phase: str, timeout: int = 3600) -> bool:
        """等待人工确认

        Args:
            phase: 阶段名称
            timeout: 超时时间（秒）

        Returns:
            如果确认通过返回 True，否则返回 False
        """
        start_time = time.time()
        approved_path = self._approved_path(phase)
        poll_interval = 0.1

        while time.time() - start_time < timeout:
            if approved_path.exists():
                data = self.store.read_json(str(approved_path), default={})
                if data.get("approved", False):
                    print(f"✅ 阶段 {phase} 已通过审核")
                    return True
            time.sleep(poll_interval)

        print(f"❌ 阶段 {phase} 审核超时")
        return False

    def request_intervention(self, task_id: str, error: str, context: dict[str, Any]) -> None:
        """请求人工介入

        Args:
            task_id: 任务 ID
            error: 错误信息
            context: 上下文信息
        """
        pending_path = Path(self.store.workspace) / self.GATES_DIR / "intervention_pending.json"
        self.store.write_json(str(pending_path), {
            "task_id": task_id,
            "error": error,
            "context": context,
            "timestamp": datetime.now().isoformat()
        })

        self._print_intervention_prompt(task_id, error)

    def wait_for_intervention(self, timeout: int = 3600) -> bool:
        """等待人工介入解决

        Args:
            timeout: 超时时间（秒）

        Returns:
            如果问题解决返回 True，否则返回 False
        """
        start_time = time.time()
        resolved_path = Path(self.store.workspace) / self.GATES_DIR / "intervention_resolved.json"
        poll_interval = 0.1

        while time.time() - start_time < timeout:
            if resolved_path.exists():
                data = self.store.read_json(str(resolved_path), default={})
                if data.get("resolved", False):
                    print("✅ 人工介入完成")
                    return True
            time.sleep(poll_interval)

        print("❌ 人工介入超时")
        return False

    def approve_phase(self, phase: str, approver: str = "user") -> None:
        """批准阶段

        Args:
            phase: 阶段名称
            approver: 审批人
        """
        approved_path = self._approved_path(phase)
        self.store.write_json(str(approved_path), {
            "approved": True,
            "approver": approver,
            "timestamp": datetime.now().isoformat()
        })

    def reject_phase(self, phase: str, reason: str, approver: str = "user") -> None:
        """拒绝阶段

        Args:
            phase: 阶段名称
            reason: 拒绝原因
            approver: 审批人
        """
        approved_path = self._approved_path(phase)
        self.store.write_json(str(approved_path), {
            "approved": False,
            "reason": reason,
            "approver": approver,
            "timestamp": datetime.now().isoformat()
        })

    # ========== 内部方法 ==========

    def _approved_path(self, phase: str) -> Path:
        """获取审批状态文件路径"""
        return Path(self.store.workspace) / self.GATES_DIR / f"{phase}_approved.json"

    def _pending_path(self, phase: str) -> Path:
        """获取待审批文件路径"""
        return Path(self.store.workspace) / self.GATES_DIR / f"{phase}_pending.json"

    def _print_approval_prompt(self, phase: str, content: dict[str, Any]) -> None:
        """打印审批提示"""
        print("\n" + "=" * 60)
        print(f"⚠️  需要人工确认阶段: {phase}")
        print(f"描述: {content.get('description', '无描述')}")
        print(f"待审核文件: {self._pending_path(phase)}")
        print("\n审核通过后，请执行:")
        print(f'  echo \'{{"approved": true}}\' > {self._pending_path(phase)}')
        print("或通过程序调用:")
        print(f'  gate_controller.approve_phase("{phase}")')
        print("=" * 60 + "\n")

    def _print_intervention_prompt(self, task_id: str, error: str) -> None:
        """打印介入提示"""
        print("\n" + "=" * 60)
        print(f"⚠️  需要人工介入: 任务 {task_id}")
        print(f"错误: {error}")
        print(f"待审核文件: {Path(self.store.workspace) / self.GATES_DIR / 'intervention_pending.json'}")
        print("\n问题解决后，请执行:")
        print(f'  echo \'{{"resolved": true}}\' > {Path(self.store.workspace) / self.GATES_DIR / "intervention_resolved.json"}')
        print("=" * 60 + "\n")


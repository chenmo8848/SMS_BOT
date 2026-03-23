# -*- coding: utf-8 -*-
"""SMS Bot v6 — 任务管理服务（多组调度、持久化、原子写入）"""

import os, json, logging
from collections import deque
from datetime import datetime
from typing import Optional
from bot.config import TASK_FILE
from bot.state import AppState
from bot.models.task import TaskGroup, TaskItem, GroupState

log = logging.getLogger(__name__)


class TaskManager:
    """多任务组管理：创建、调度、持久化"""

    def __init__(self, state: AppState):
        self._state = state

    # ─── 任务组操作 ───

    def load_group_to_queue(self, g: TaskGroup):
        """将任务组加载到全局队列"""
        s = self._state
        s.task_queue.clear()
        for t in g.queue:
            s.task_queue.append(t)
        s.task_stats.update({
            "total": g.total, "sent": g.sent,
            "failed": g.failed, "start_time": datetime.now(),
        })
        g.state = GroupState.RUNNING

    def sync_group_from_queue(self, g: TaskGroup):
        """从全局队列同步回任务组"""
        s = self._state
        g.queue = deque(s.task_queue)
        g.sent = s.task_stats["sent"]
        g.failed = s.task_stats["failed"]

    def auto_resume_tasks(self) -> Optional[str]:
        """
        自动恢复因断线暂停的任务（统一逻辑，消除重复）
        返回恢复信息字符串，无需恢复则返回 None
        """
        s = self._state
        if not (s.task_running and s.task_paused):
            return None
        s.task_paused = False
        cg = s.current_group()
        if cg and cg.state == GroupState.PAUSED:
            cg.state = GroupState.RUNNING
        remaining = len(s.task_queue)
        return f"\n\n▶️ 任务已自动恢复，剩余 {remaining} 条"

    # ─── 持久化（原子写入）───

    def save(self):
        """保存所有未完成任务组"""
        try:
            groups_data = []
            for g in self._state.task_groups:
                if g.state in (GroupState.RUNNING, GroupState.PAUSED, GroupState.QUEUED) and g.queue:
                    if g.state == GroupState.RUNNING:
                        self.sync_group_from_queue(g)
                    groups_data.append(g.to_dict())
            tmp = TASK_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({
                    "groups": groups_data,
                    "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, TASK_FILE)
        except Exception as e:
            log.warning(f"保存任务失败: {e}")

    def load(self) -> list[TaskGroup]:
        """从文件恢复任务组（兼容旧格式）"""
        if not os.path.exists(TASK_FILE):
            return []
        try:
            with open(TASK_FILE, encoding="utf-8") as f:
                data = json.load(f)
            # 新格式
            if "groups" in data:
                return [TaskGroup.from_dict(g) for g in data["groups"]]
            # 旧格式兼容
            tasks = data.get("tasks", [])
            if tasks:
                stats = data.get("stats", {})
                return [TaskGroup.from_dict({
                    "id": "T000", "name": "恢复任务", "tasks": tasks,
                    "total": stats.get("total", len(tasks)),
                    "sent": stats.get("sent", 0), "failed": stats.get("failed", 0),
                    "state": "paused",
                })]
            return []
        except Exception as e:
            log.warning(f"读取任务失败: {e}")
            return []

    def clear(self):
        """清除任务文件"""
        try:
            if os.path.exists(TASK_FILE):
                os.remove(TASK_FILE)
        except Exception as e:
            log.warning(f"清除任务文件失败: {e}")

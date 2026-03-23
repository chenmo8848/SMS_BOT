# -*- coding: utf-8 -*-
"""SMS Bot v6 — 任务数据模型"""

from dataclasses import dataclass, field
from collections import deque
from datetime import datetime
from enum import Enum
from typing import Optional


class GroupState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    STOPPED = "stopped"


@dataclass
class TaskItem:
    phone: str
    message: str


@dataclass
class TaskGroup:
    id: str
    name: str
    queue: deque = field(default_factory=deque)
    total: int = 0
    sent: int = 0
    failed: int = 0
    state: GroupState = GroupState.QUEUED
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def remaining(self) -> int:
        return len(self.queue)

    @property
    def done(self) -> int:
        return self.sent + self.failed

    @property
    def progress_pct(self) -> int:
        return int(self.sent / self.total * 100) if self.total else 0

    @property
    def progress_bar(self) -> str:
        pct = self.progress_pct
        done_blocks = pct // 10
        return "█" * done_blocks + "░" * (10 - done_blocks)

    @property
    def state_icon(self) -> str:
        return {
            GroupState.RUNNING: "▶️",
            GroupState.PAUSED: "⏸",
            GroupState.QUEUED: "⏳",
            GroupState.COMPLETED: "✅",
            GroupState.STOPPED: "⏹",
        }.get(self.state, "❓")

    @property
    def state_text(self) -> str:
        return {
            GroupState.RUNNING: "发送中",
            GroupState.PAUSED: "已暂停",
            GroupState.QUEUED: "排队中",
            GroupState.COMPLETED: "已完成",
            GroupState.STOPPED: "已停止",
        }.get(self.state, "未知")

    def to_dict(self) -> dict:
        """序列化为可 JSON 存储的字典"""
        return {
            "id": self.id,
            "name": self.name,
            "tasks": [{"phone": t.phone, "message": t.message} for t in self.queue],
            "total": self.total,
            "sent": self.sent,
            "failed": self.failed,
            "state": self.state.value,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TaskGroup":
        """从字典恢复"""
        items = deque(TaskItem(**t) for t in d.get("tasks", []))
        return cls(
            id=d.get("id", "T000"),
            name=d.get("name", "恢复任务"),
            queue=items,
            total=d.get("total", len(items)),
            sent=d.get("sent", 0),
            failed=d.get("failed", 0),
            state=GroupState(d.get("state", "paused")),
            created_at=datetime.now(),
        )

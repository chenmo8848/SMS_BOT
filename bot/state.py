# -*- coding: utf-8 -*-
"""SMS Bot v6 — 集中状态管理（替代 15+ 全局变量）"""

import asyncio
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime
from typing import Optional

from bot.models.task import TaskGroup, TaskItem, GroupState


@dataclass
class AppState:
    """
    全局可变状态的唯一持有者。
    所有需要读写运行时状态的模块都通过这个对象访问，不再用 global。
    """

    # ── 任务 ──
    task_running: bool = False
    task_paused: bool = False
    global_paused: bool = False      # 全局暂停：停发送，不影响监控和短信通知
    task_queue: deque = field(default_factory=deque)
    task_groups: list[TaskGroup] = field(default_factory=list)
    task_stats: dict = field(default_factory=lambda: {
        "total": 0, "sent": 0, "failed": 0, "start_time": None
    })

    # ── 监控 ──
    monitor_active: bool = False
    pl_last_state: Optional[str] = None

    # ── 落地测试 ──
    test_active: bool = False
    test_running: bool = False
    land_test_hold: bool = False     # 落地测试强制暂停标志

    # ── 授权 ──
    license_blocked: bool = False    # 授权未通过时锁定所有功能

    # ── 短信回复优先级抢占（独立计数，不再共享 bool）──
    _priority_hold_count: int = 0

    # ── 模板 ──
    sms_template: str = "{姓名}您好，您尾号 {卡号} 的银行卡于 {日期}申请的 {金额} 元。"

    # ── 短信回复映射：Telegram 消息ID → 发件人号码 ──
    sms_reply_map: dict[int, str] = field(default_factory=dict)
    SMS_REPLY_MAP_MAX: int = 200

    # ── 发送引擎运行时状态（auto 模式用）──
    engine_resolved: Optional[str] = None   # 首次 UIA 成功后记住

    # ── 内部计数器 ──
    _tg_counter: int = 0

    # ── 发送互斥锁（asyncio 层面）──
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def next_tg_id(self) -> str:
        self._tg_counter += 1
        return f"T{self._tg_counter:03d}"

    # ── 优先级抢占管理（落地测试、短信回复各自独立）──

    def acquire_priority(self):
        """申请抢占发送优先级（可多个同时持有）"""
        self._priority_hold_count += 1

    def release_priority(self):
        """释放抢占"""
        self._priority_hold_count = max(0, self._priority_hold_count - 1)

    @property
    def priority_held(self) -> bool:
        """是否有任何抢占者持有优先级"""
        return self._priority_hold_count > 0 or self.land_test_hold

    # ── 任务组操作 ──

    def create_group(self, name: str, tasks: list[dict]) -> TaskGroup:
        gid = self.next_tg_id()
        items = deque(TaskItem(**t) for t in tasks)
        g = TaskGroup(
            id=gid, name=name, queue=items,
            total=len(tasks), created_at=datetime.now(),
        )
        self.task_groups.append(g)
        return g

    def get_group(self, gid: str) -> Optional[TaskGroup]:
        for g in self.task_groups:
            if g.id == gid:
                return g
        return None

    def active_groups(self) -> list[TaskGroup]:
        return [g for g in self.task_groups
                if g.state in (GroupState.RUNNING, GroupState.PAUSED, GroupState.QUEUED)]

    def current_group(self) -> Optional[TaskGroup]:
        for g in self.task_groups:
            if g.state == GroupState.RUNNING:
                return g
        return None

    def pick_next_group(self) -> Optional[TaskGroup]:
        for g in self.task_groups:
            if g.state == GroupState.QUEUED and g.queue:
                return g
        return None

    def task_summary(self) -> str:
        ag = self.active_groups()
        if not ag:
            return "⚪ 无任务"
        parts = []
        running = [g for g in ag if g.state == GroupState.RUNNING]
        paused = [g for g in ag if g.state == GroupState.PAUSED]
        queued = [g for g in ag if g.state == GroupState.QUEUED]
        if running:
            g = running[0]
            parts.append(f"🟢 发送中 {g.sent}/{g.total}")
        if paused:
            parts.append(f"⏸ {len(paused)}组暂停")
        if queued:
            parts.append(f"⏳ {len(queued)}组排队")
        return "　".join(parts) if parts else "⚪ 无任务"

    def cleanup_reply_map(self):
        """清理过多的短信回复映射，防内存泄漏"""
        if len(self.sms_reply_map) > self.SMS_REPLY_MAP_MAX:
            oldest = sorted(self.sms_reply_map.keys())[
                : len(self.sms_reply_map) - self.SMS_REPLY_MAP_MAX
            ]
            for k in oldest:
                self.sms_reply_map.pop(k, None)

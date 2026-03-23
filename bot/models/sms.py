# -*- coding: utf-8 -*-
"""SMS Bot v6 — 短信相关数据模型"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SmsMessage:
    message_id: int
    from_address: str
    body: str
    timestamp: Optional[int] = None


@dataclass
class SimCard:
    subscription_id: int
    sim_slot_index: int
    name: str
    number: str
    is_default: bool

    @property
    def display(self) -> str:
        mark = "✅" if self.is_default else "☐"
        return f"{mark} 卡{self.sim_slot_index + 1} · {self.name} · {self.number}"

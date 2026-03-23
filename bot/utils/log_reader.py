# -*- coding: utf-8 -*-
"""SMS Bot v6 — 日志读取工具"""

import os
from bot.config import LOG_FILE


def read_log_tail(n: int = 30, level: str = None) -> str:
    """读取日志最后 n 行，可选按级别过滤"""
    if not os.path.exists(LOG_FILE):
        return "（暂无日志）"
    try:
        with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        if level:
            all_lines = [l for l in all_lines if f"[{level}]" in l]
        tail = all_lines[-n:] if len(all_lines) > n else all_lines
        return "".join(tail).strip() or "（暂无日志）"
    except Exception as e:
        return f"读取失败: {e}"


def get_log_bytes() -> bytes:
    """读取完整日志文件为 bytes"""
    if not os.path.exists(LOG_FILE):
        return "（暂无日志）".encode("utf-8")
    try:
        with open(LOG_FILE, "rb") as f:
            return f.read()
    except Exception as e:
        return f"读取失败: {e}".encode("utf-8")


def get_log_size() -> str:
    """获取日志文件大小（人类可读）"""
    if not os.path.exists(LOG_FILE):
        return "0 B"
    try:
        size = os.path.getsize(LOG_FILE)
        for unit in ["B", "KB", "MB"]:
            if size < 1024:
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"
    except Exception:
        return "未知"


def clear_log_file() -> bool:
    """清空日志文件"""
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("")
        return True
    except Exception:
        return False

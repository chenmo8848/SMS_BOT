# -*- coding: utf-8 -*-
"""SMS Bot v6 — Phone Link 进程管理（三层状态检测、重启、确保运行）"""

import subprocess, time, logging
from typing import Optional
from bot.config import RESTART_PS1
from bot.services.phone_db import PhoneDB

log = logging.getLogger(__name__)

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


class PhoneLinkManager:
    """Phone Link 进程管理"""

    def __init__(self, db: PhoneDB):
        self._db = db

    def get_status(self) -> str:
        """
        三层检测手机连接真实状态：
        1. 进程是否存在 → offline
        2. phone.db 是否在更新 → disconnected
        3. 窗口是否卡死 → frozen（仅在 DB 活跃时检查）
        全部通过 → online
        """
        try:
            # ── 层1：进程检测 ──
            procs = []
            proc_alive = False

            if HAS_PSUTIL:
                procs = [p for p in psutil.process_iter(["name", "pid"])
                         if "PhoneExperienceHost" in (p.info["name"] or "")]
                proc_alive = len(procs) > 0
            else:
                try:
                    r = subprocess.run(
                        ["tasklist", "/FI", "IMAGENAME eq PhoneExperienceHost.exe",
                         "/FO", "CSV", "/NH"],
                        capture_output=True, text=True, timeout=5, errors="replace",
                    )
                    proc_alive = "PhoneExperienceHost" in r.stdout
                except Exception:
                    pass

            if not proc_alive:
                return "offline"

            # ── 层2：phone.db 活跃度 ──
            age = self._db.get_db_age_seconds()
            if age is None:
                return "disconnected"
            if age > 300:
                return "disconnected"

            # ── 层3：窗口卡死检测（仅在 DB 活跃时）──
            try:
                import ctypes
                user32 = ctypes.windll.user32
                EnumWindowsProc = ctypes.WINFUNCTYPE(
                    ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)
                )
                hung = [False]

                def check_window(hwnd_val, _):
                    pid = ctypes.c_ulong()
                    user32.GetWindowThreadProcessId(hwnd_val, ctypes.byref(pid))
                    if HAS_PSUTIL:
                        for p in procs:
                            if p.info["pid"] == pid.value:
                                if user32.IsHungAppWindow(hwnd_val):
                                    hung[0] = True
                                    return False
                    return True

                user32.EnumWindows(EnumWindowsProc(check_window), 0)
                if hung[0]:
                    return "frozen"
            except Exception:
                pass

            return "online"

        except Exception as e:
            log.error(f"get_status error: {e}")
            return "offline"

    @staticmethod
    def status_text(st: str) -> str:
        """状态码 → 显示文字"""
        return {
            "online":       "✅ 运行中",
            "offline":      "❌ 未运行",
            "frozen":       "⚠️ 无响应（卡死）",
            "disconnected": "📵 手机可能已断开",
        }.get(st, "❓ 未知")

    def is_running(self) -> bool:
        """轻量检测：只查进程是否存在"""
        try:
            r = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq PhoneExperienceHost.exe"],
                capture_output=True, text=True, timeout=10, errors="replace",
            )
            return "PhoneExperienceHost" in r.stdout
        except Exception:
            return False

    def restart(self) -> bool:
        """强制重启：调用 restart_phonelink.ps1"""
        log.info("调用 restart_phonelink.ps1")
        try:
            r = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File", RESTART_PS1],
                capture_output=True, text=True, timeout=90, errors="replace",
            )
            if "OK" in r.stdout:
                log.info("重启成功")
                return True
            log.warning(f"重启失败: {r.stdout.strip()!r}")
            return False
        except subprocess.TimeoutExpired:
            log.error("重启超时(90s)")
            return False
        except Exception as e:
            log.error(f"重启异常: {e}")
            return False

    def ensure_running(self) -> bool:
        """确保 Phone Link 在运行，未运行则自动启动"""
        if not self.is_running():
            log.info("Phone Link 未运行，自动启动...")
            subprocess.Popen(["explorer.exe", "ms-yourphone://"])
            time.sleep(6)
            return self.is_running()
        return True

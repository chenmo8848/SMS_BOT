# -*- coding: utf-8 -*-
"""SMS Bot v6 — 短信发送服务（发送 + DB确认 + auto引擎模式）"""

import asyncio, subprocess, time, logging
from bot.config import BotConfig, SEND_PS1
from bot.services.phone_db import PhoneDB
from bot.services.phone_link import PhoneLinkManager
from bot.state import AppState
from bot.utils.formatting import normalize_phone

log = logging.getLogger(__name__)


class SmsSender:
    """短信发送服务（asyncio 层面互斥）"""

    def __init__(self, cfg: BotConfig, state: AppState,
                 db: PhoneDB, pl: PhoneLinkManager):
        self._cfg = cfg
        self._state = state
        self._db = db
        self._pl = pl

    async def send(self, phone: str, message: str) -> tuple[bool, str]:
        """
        发送短信（异步入口）
        - 授权轻量检查
        - asyncio.Lock 保证一次只有一个发送
        - 在线程池中执行阻塞的 PowerShell 调用
        """
        # 授权轻量检查（不联网，只查内存 + 过期时间）
        license_mgr = getattr(self, '_license_mgr', None)
        if license_mgr and not license_mgr.light_check():
            return False, "授权已过期或无效，请发 /activate 重新验证"

        phone = normalize_phone(phone)
        if not phone:
            return False, "号码为空"

        try:
            await asyncio.wait_for(self._state.send_lock.acquire(), timeout=120)
        except asyncio.TimeoutError:
            return False, "发送队列拥堵，请稍后重试"

        try:
            loop = asyncio.get_running_loop()
            # 在获取锁之后、进入线程池之前读取引擎设置
            engine = self._resolve_engine()
            result = await loop.run_in_executor(
                None, self._blocking_send, phone, message, engine
            )
            return result
        finally:
            self._state.send_lock.release()

    def _resolve_engine(self) -> str:
        """解析实际使用的引擎"""
        engine = self._cfg.send_engine
        if engine != "auto":
            return engine
        # auto 模式：如果之前 UIA 成功过，直接用 UIA
        if self._state.engine_resolved:
            return self._state.engine_resolved
        # 否则传 auto 给 PS1，让它先试 UIA 再降级
        return "auto"

    def _blocking_send(self, phone: str, message: str, engine: str) -> tuple[bool, str]:
        """阻塞发送（在线程池中执行）"""
        self._pl.ensure_running()
        before_id = self._db.get_max_sent_id()

        # 调用 PowerShell
        try:
            r = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass",
                 "-File", SEND_PS1, phone, message, engine],
                capture_output=True, text=True,
                errors="replace", timeout=90,
            )
        except subprocess.TimeoutExpired:
            return False, "超时(90s)"
        except Exception as e:
            return False, str(e)

        stdout = r.stdout.strip()
        if "FAIL" in stdout or (r.returncode != 0 and "OK" not in stdout):
            err = (stdout or r.stderr.strip() or "未知错误")[:200]
            log.error(f"发送失败(PS1): {err}")
            return False, f"Phone Link 操作失败: {err}"

        # 检测 auto 模式下实际用了哪个引擎
        if self._cfg.send_engine == "auto" and not self._state.engine_resolved:
            if "UIA" in stdout and "fallback" not in stdout.lower():
                self._state.engine_resolved = "uia"
                log.info("auto 模式：UIA 首次成功，后续优先 UIA")
            elif "SendKeys" in stdout or "fallback" in stdout.lower():
                self._state.engine_resolved = "sendkeys"
                log.info("auto 模式：降级到 SendKeys")

        # 轮询 DB 确认
        confirmed = self._db.confirm_sent(before_id, phone=phone, timeout=15)
        if confirmed:
            log.info(f"已发送(DB确认) → {phone} | {message[:40]}")
            return True, "DB确认已发出"
        else:
            log.warning(f"发送未确认(DB无新记录) → {phone}")
            return False, "操作完成但数据库未确认（可能未发出）"
        # finally: 发送后等 1 秒让 Phone Link 恢复
        # 注意：这个等待在 asyncio.Lock 释放之前，是有意的

# -*- coding: utf-8 -*-
"""SMS Bot v6 — 监控服务（三层检测 + 状态转换表 + 统一恢复逻辑）"""

import asyncio, logging
from telegram import Bot
from bot.config import BotConfig
from bot.state import AppState
from bot.services.phone_db import PhoneDB
from bot.services.phone_link import PhoneLinkManager
from bot.services.notifier import Notifier
from bot.services.task_manager import TaskManager

log = logging.getLogger(__name__)


class MonitorService:
    """三层监控 + 短信检测，解耦自 Telegram"""

    def __init__(self, cfg: BotConfig, state: AppState,
                 db: PhoneDB, pl: PhoneLinkManager,
                 notifier: Notifier, task_mgr: TaskManager):
        self._cfg = cfg
        self._state = state
        self._db = db
        self._pl = pl
        self._notifier = notifier
        self._task_mgr = task_mgr

    async def run(self, bot: Bot):
        """监控主循环"""
        s = self._state
        s.monitor_active = True
        log.info(f"监控启动 | 连接:{self._cfg.mon_status_sec}s | 短信:{self._cfg.mon_sms_sec}s")

        last_msg_id = self._db.get_max_message_id()
        log.info(f"当前最大 message_id：{last_msg_id}")

        # 初始化状态检测
        loop = asyncio.get_running_loop()
        init = await loop.run_in_executor(None, self._pl.get_status)
        log.info(f"手机连接初始状态：{init}")

        await self._handle_init_state(bot, init, loop)

        tick = 0
        last_status = -self._cfg.mon_status_sec
        last_sms = -self._cfg.mon_sms_sec

        while s.monitor_active:
            try:
                await asyncio.sleep(1)
                tick += 1

                # ── 连接状态检测 ──
                if tick - last_status >= self._cfg.mon_status_sec:
                    last_status = tick
                    await self._check_connection(bot, loop)

                # ── 短信检测 ──
                if tick - last_sms >= self._cfg.mon_sms_sec:
                    last_sms = tick
                    last_msg_id = await self._check_sms(bot, last_msg_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"监控循环异常: {e}", exc_info=True)
                await asyncio.sleep(5)

        s.monitor_active = False
        log.info("监控已停止")

    # ─── 初始状态处理 ───

    async def _handle_init_state(self, bot: Bot, init: str, loop):
        s = self._state
        if init == "offline":
            s.pl_last_state = "offline"
            await self._notifier.send(bot, "📵 *手机连接未运行*\n\n正在尝试启动...")
            ok = await loop.run_in_executor(None, self._pl.restart)
            if ok:
                s.pl_last_state = "online"
                await self._notifier.send(bot, "✅ *手机连接已启动*")
            else:
                await self._notifier.send(bot, "❌ *启动失败*，请手动打开手机连接")
        elif init == "frozen":
            s.pl_last_state = "frozen"
            await self._notifier.send(bot, "⚠️ *手机连接无响应*\n\n正在重启...")
            ok = await loop.run_in_executor(None, self._pl.restart)
            s.pl_last_state = "online" if ok else "frozen"
        elif init == "disconnected":
            s.pl_last_state = "disconnected"
            await self._notifier.send(bot, "📵 *手机可能已断开*\n\n请检查蓝牙和 WiFi")
        else:
            s.pl_last_state = "online"
            await self._notifier.send(bot, "📡 监控已启动，手机连接正常", parse_mode=None)

    # ─── 状态转换表（统一处理，消除重复代码）───

    async def _check_connection(self, bot: Bot, loop):
        s = self._state
        try:
            cur = await loop.run_in_executor(None, self._pl.get_status)
            old = s.pl_last_state

            # 需要暂停任务 + 重启的情况
            if cur in ("offline", "frozen") and old == "online":
                s.pl_last_state = cur
                label = "通信基站离线" if cur == "offline" else "基站信号卡顿"
                log.warning(f"手机连接异常: {old} → {cur}")
                self._pause_tasks_if_running()
                await self._notifier.send(bot, f"⚠️ *{label}*\n\n正在尝试重启...")
                ok = await loop.run_in_executor(None, self._pl.restart)
                if ok:
                    s.pl_last_state = "online"
                    resume = self._task_mgr.auto_resume_tasks() or ""
                    await self._notifier.send(bot, f"✅ *通信恢复！基站重新上线*{resume}")
                else:
                    await self._notifier.send(bot, "❌ *重启失败*\n\n请手动打开手机连接")

            # 恢复在线
            elif cur == "online" and old in ("offline", "frozen", "disconnected"):
                s.pl_last_state = "online"
                log.info("手机连接已恢复正常")
                resume = self._task_mgr.auto_resume_tasks() or ""
                await self._notifier.send(bot, f"✅ *连接已恢复*{resume}")

            # 手机脱机
            elif cur == "disconnected" and old == "online":
                s.pl_last_state = "disconnected"
                log.warning("手机可能已断开（phone.db 超过5分钟未更新）")
                self._pause_tasks_if_running()
                cg = s.current_group()
                if cg and cg.state.value == "running":
                    from bot.models.task import GroupState
                    cg.state = GroupState.PAUSED
                await self._notifier.send(
                    bot,
                    "📵 *手机已断开*\n\n"
                    "数据库超过 5 分钟未更新\n"
                    "请检查手机蓝牙/WiFi\n\n"
                    "连接恢复后任务将自动继续"
                )

        except Exception as e:
            log.error(f"连接状态检测异常: {e}")

    def _pause_tasks_if_running(self):
        """暂停正在运行的任务"""
        s = self._state
        if s.task_running and not s.task_paused:
            s.task_paused = True

    # ─── 短信检测 ───

    async def _check_sms(self, bot: Bot, last_msg_id: int) -> int:
        """检测新收到的短信，返回更新后的 last_msg_id"""
        try:
            new_msgs = self._db.read_new_sms(since_id=last_msg_id)
            for msg in new_msgs:
                if msg.message_id > last_msg_id:
                    last_msg_id = msg.message_id
                from datetime import datetime
                now = datetime.now().strftime("%H:%M:%S")
                log.info(f"新短信 from {msg.from_address}: {msg.body[:40]}")
                sms_text = (
                    f"📩 收到新短信\n"
                    f"━━━━━━━━━━━━━━━\n\n"
                    f"时间：{now}\n"
                    f"发件人：{msg.from_address}\n"
                    f"内容：{msg.body}\n\n"
                    f"💬 回复此消息可直接回复短信"
                )
                sent_msg = await self._notifier.send(bot, sms_text, parse_mode=None)
                if sent_msg and msg.from_address:
                    s = self._state
                    s.sms_reply_map[sent_msg.message_id] = msg.from_address
                    s.cleanup_reply_map()
        except Exception as e:
            log.error(f"短信检测异常: {e}")
        return last_msg_id

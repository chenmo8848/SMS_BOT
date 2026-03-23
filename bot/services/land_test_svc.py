# -*- coding: utf-8 -*-
"""SMS Bot v6 — 落地测试服务（最高优先级，Event 信号真正等待）"""

import asyncio, logging
from datetime import datetime
from telegram import Bot
from bot.config import BotConfig
from bot.state import AppState
from bot.services.sms_sender import SmsSender
from bot.services.phone_db import PhoneDB
from bot.services.notifier import Notifier

log = logging.getLogger(__name__)


class LandTestService:
    """落地测试：定时发送测试短信验证通道"""

    def __init__(self, cfg: BotConfig, state: AppState,
                 sender: SmsSender, db: PhoneDB, notifier: Notifier):
        self._cfg = cfg
        self._state = state
        self._sender = sender
        self._db = db
        self._notifier = notifier

    async def run(self, bot: Bot):
        """落地测试主循环"""
        s = self._state
        s.test_active = True
        phone = self._cfg.test_phone
        interval = self._cfg.test_interval_min
        log.info(f"落地测试启动 | 间隔:{interval}分钟 | 号码:{phone}")

        first_run = True
        while s.test_active:
            try:
                if first_run:
                    await asyncio.sleep(10)
                    first_run = False
                else:
                    await asyncio.sleep(interval * 60)

                if not s.test_active:
                    break
                if not phone:
                    log.warning("落地测试：未设置测试号码，跳过")
                    continue
                if s.test_running:
                    log.warning("落地测试：上次尚未完成，跳过")
                    continue
                if s.global_paused:
                    log.info("落地测试：全局暂停中，跳过")
                    continue

                s.test_running = True

                # 获取测试内容
                try:
                    body = self._db.get_last_sent_body() or self._cfg.test_content
                except Exception:
                    body = self._cfg.test_content
                if not body:
                    body = "落地测试"

                now_str = datetime.now().strftime("%H:%M")
                await self._notifier.send(
                    bot,
                    f"📡 *试射开始* — {now_str}\n"
                    f"━━━━━━━━━━━━━━━\n\n"
                    f"🎯 目标：{phone}\n"
                    f"💬 弹药：{body[:40]}"
                )

                # ── 最高优先级：通过 acquire_priority 暂停批量 ──
                had_running = s.task_running and not s.priority_held
                if had_running:
                    s.acquire_priority()
                    s.land_test_hold = True
                    log.info("落地测试：暂停批量任务，等待当前发送完成")
                    # 真正等待：尝试获取发送锁，说明当前发送已完成
                    try:
                        await asyncio.wait_for(s.send_lock.acquire(), timeout=100)
                        s.send_lock.release()  # 立即释放，只是用来等待
                    except asyncio.TimeoutError:
                        log.warning("落地测试：等待发送完成超时，强制继续")

                try:
                    ok, info = await self._sender.send(phone, body)
                    result = "✅ 试射成功，通道正常" if ok else f"❌ 试射失败：{info}"
                except Exception as e:
                    result = f"❌ 试射异常：{e}"
                finally:
                    if had_running:
                        s.land_test_hold = False
                        s.release_priority()
                        log.info("落地测试完成：恢复批量任务")
                    s.test_running = False

                await self._notifier.send(
                    bot,
                    f"📡 *试射报告*\n"
                    f"━━━━━━━━━━━━━━━\n\n"
                    f"🎯 {phone}\n"
                    f"{result}"
                )
                log.info(f"落地测试 → {phone} | {result}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"落地测试异常: {e}", exc_info=True)
                s.land_test_hold = False
                s.test_running = False
                if s._priority_hold_count > 0:
                    s.release_priority()
                await asyncio.sleep(10)

        s.test_active = False
        s.land_test_hold = False
        log.info("落地测试已停止")

# -*- coding: utf-8 -*-
"""
SMS Bot v6 — 启动入口
运行方式：python -m bot
"""

import os, sys, logging, threading, traceback, asyncio
from datetime import datetime
from collections import deque

# ── 崩溃日志（最先绑定）──
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BOT_DIR)

from bot.config import write_crash, load_config, CRASH_LOG, LOG_FILE

# ── 第三方库导入 ──
try:
    from telegram import Update, BotCommand
    from telegram.request import HTTPXRequest
    from telegram.ext import ApplicationBuilder, ContextTypes
except ImportError as e:
    write_crash(f"导入失败: {e}\n请运行: venv\\Scripts\\pip install python-telegram-bot httpx pydantic")
    sys.exit(1)

# ── 配置加载（启动即校验）──
try:
    cfg = load_config()
except SystemExit:
    raise
except Exception as e:
    write_crash(f"配置加载失败: {e}\n{traceback.format_exc()}")
    sys.exit(1)

# ── 日志 ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
for name in ("httpx", "httpcore", "telegram", "apscheduler"):
    logging.getLogger(name).setLevel(logging.WARNING)
log = logging.getLogger(__name__)

# ── 全局异常钩子 ──
def _except_hook(exc_type, exc_value, exc_tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    write_crash(f"未捕获异常（主线程）:\n{msg}")
    log.critical(f"未捕获异常: {exc_value}", exc_info=(exc_type, exc_value, exc_tb))

sys.excepthook = _except_hook

def _thread_except_hook(args):
    if issubclass(args.exc_type, SystemExit):
        return
    msg = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
    write_crash(f"线程异常 [{args.thread}]:\n{msg}")
    log.critical(f"线程异常: {args.exc_value}", exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

threading.excepthook = _thread_except_hook
log.info("崩溃日志已启用: %s", CRASH_LOG)


def main():
    # ── 初始化共享对象 ──
    from bot.state import AppState
    from bot.services.phone_db import PhoneDB
    from bot.services.phone_link import PhoneLinkManager
    from bot.services.sms_sender import SmsSender
    from bot.services.notifier import Notifier
    from bot.services.task_manager import TaskManager
    from bot.services.monitor_svc import MonitorService
    from bot.services.land_test_svc import LandTestService
    from bot.services.license import LicenseManager
    from bot.handlers.register import register_all
    from bot.utils.formatting import fishing_quote

    state = AppState()
    db = PhoneDB()
    pl = PhoneLinkManager(db)
    sender = SmsSender(cfg, state, db, pl)
    notifier = Notifier(cfg)
    task_mgr = TaskManager(state)
    monitor_svc = MonitorService(cfg, state, db, pl, notifier, task_mgr)
    landtest_svc = LandTestService(cfg, state, sender, db, notifier)
    license_mgr = LicenseManager(cfg.license_api_url)
    sender._license_mgr = license_mgr  # 注入授权检查

    # ── 构建 Application ──
    kw = {"connection_pool_size": 8}
    if cfg.proxy:
        kw["proxy"] = cfg.proxy

    app = (
        ApplicationBuilder()
        .token(cfg.bot_token)
        .request(HTTPXRequest(**kw))
        .get_updates_request(HTTPXRequest(**kw))
        .build()
    )

    # ── 注入共享对象到 bot_data ──
    app.bot_data["cfg"] = cfg
    app.bot_data["state"] = state
    app.bot_data["db"] = db
    app.bot_data["pl"] = pl
    app.bot_data["sender"] = sender
    app.bot_data["notifier"] = notifier
    app.bot_data["task_mgr"] = task_mgr
    app.bot_data["monitor_svc"] = monitor_svc
    app.bot_data["landtest_svc"] = landtest_svc
    app.bot_data["license_mgr"] = license_mgr

    # ── 注册 handler ──
    register_all(app)

    # ── 启动后回调 ──
    async def post_init(application):
        bot = application.bot
        await bot.set_my_commands([
            BotCommand("start",         "打开主菜单"),
            BotCommand("help",          "使用指南"),
            BotCommand("status",        "查看发送进度"),
            BotCommand("batch",         "批量导入"),
            BotCommand("send",          "单发：/send 号码 内容"),
            BotCommand("template",      "查看/修改模板"),
            BotCommand("pause",         "暂停发送"),
            BotCommand("resume",        "继续发送"),
            BotCommand("stop",          "停止发送"),
            BotCommand("settings",      "查看设置"),
        ])

        # ── 授权验证（联网）──
        lic_status_line = ""
        if cfg.license_api_url:
            log.info("正在验证授权...")
            lic_ok, lic_msg = license_mgr.full_verify()
            if not lic_ok:
                log.warning(f"授权验证失败: {lic_msg}")
                from bot.handlers.license import show_license_blocked
                await show_license_blocked(bot, cfg, license_mgr)
                state.license_blocked = True
                log.info("授权未通过，功能已锁定")
                return  # 不执行后续启动流程
            else:
                log.info(f"授权验证通过: {lic_msg}")
                # 构建授权状态行
                vr = license_mgr.last_verify_result or {}
                if vr.get("trial"):
                    hours = vr.get("trial_hours_left", 24)
                    lic_status_line = f"\n🔵 试用中（剩余 {hours} 小时）"
                elif license_mgr.expires == "permanent":
                    lic_status_line = "\n🟢 永久授权"
                elif license_mgr.expires:
                    days = vr.get("days_left", 0)
                    if days <= 7:
                        lic_status_line = f"\n⚠️ 授权即将到期（剩 {days} 天，{license_mgr.expires}）"
                    else:
                        lic_status_line = f"\n🟢 授权至 {license_mgr.expires}（剩 {days} 天）"
        else:
            log.info("未配置授权服务器，跳过验证")

        # 启动通知
        quote = fishing_quote()
        await notifier.send(
            bot,
            "🎣 *捕鱼达人 v6* 🐟\n"
            "━━━━━━━━━━━━━━━━━\n\n"
            + quote + lic_status_line + "\n\n"
            "老板请上船 👉 /start"
        )

        # ── 启动到期提醒定时任务 ──
        if cfg.license_api_url:
            asyncio.create_task(_expiry_reminder_loop(bot, cfg, license_mgr, notifier, state))

        # 自动启动监控
        log.info("自动启动监控")
        asyncio.create_task(monitor_svc.run(bot))

        # 恢复未完成任务
        saved = task_mgr.load()
        if saved:
            total_tasks = 0
            for g in saved:
                if g.queue:
                    state.task_groups.append(g)
                    total_tasks += len(g.queue)
            if total_tasks:
                from bot.models.task import GroupState
                await notifier.send(
                    bot,
                    f"🔔 *上次出海未归！*\n━━━━━━━━━━━━━━━\n\n"
                    f"📦 {len(state.task_groups)} 组任务　{total_tasks} 条弹药\n\n"
                    "▶️ /resume_tasks → 继续捕捞\n"
                    "🗑 /clear_tasks → 丢弃弹药"
                )
                log.info(f"恢复 {len(state.task_groups)} 组 {total_tasks} 条待发任务")

                # 落地测试提示
                if cfg.test_enabled and cfg.test_phone:
                    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                    await bot.send_message(
                        chat_id=cfg.notify_user_id,
                        text=f"📡 *是否开启落地测试？*\n\n"
                             f"📞 {cfg.test_phone}　⏱ 每 {cfg.test_interval_min} 分钟",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("✅ 开启", callback_data="cb_landtest_auto_on"),
                            InlineKeyboardButton("⏭ 跳过", callback_data="cb_landtest_auto_skip"),
                        ]]),
                    )

        log.info("启动通知已发送")

    async def _expiry_reminder_loop(bot, cfg, license_mgr, notifier, state):
        """定期检查授权到期，提前提醒"""
        import asyncio as _aio
        from bot.services.license import verify_online
        # 首次等 1 小时再检查
        await _aio.sleep(3600)
        while True:
            try:
                if state.license_blocked:
                    await _aio.sleep(3600)
                    continue
                result = verify_online(license_mgr.machine_id, cfg.license_api_url)
                # 更新管理员联系方式
                if result.get("admin_contact"):
                    license_mgr._admin_contact = result["admin_contact"]
                admin = license_mgr.admin_link

                if not result.get("valid"):
                    state.license_blocked = True
                    msg = result.get("msg", "授权已失效")
                    await notifier.send(
                        bot,
                        f"🔴 *授权已失效*\n━━━━━━━━━━━━━━━\n\n"
                        f"{msg}\n\n请联系 {admin} 续期",
                    )
                    log.warning(f"授权失效: {msg}")
                    break

                # 试用到期提醒
                if result.get("trial"):
                    hours = result.get("trial_hours_left", 0)
                    if hours <= 6 and hours > 0:
                        await notifier.send(
                            bot,
                            f"⚠️ *试用即将结束*\n\n"
                            f"剩余 {hours} 小时\n"
                            f"请联系 {admin} 购买授权",
                            parse_mode="Markdown",
                        )
                    elif hours <= 0:
                        state.license_blocked = True
                        await notifier.send(
                            bot,
                            f"🔴 *24小时试用已结束*\n\n请联系 {admin} 购买授权",
                        )
                        break

                # 正式授权到期提醒（7天、3天、1天）
                days_left = result.get("days_left", -1)
                if days_left in (7, 3, 1):
                    await notifier.send(
                        bot,
                        f"⚠️ *授权即将到期*\n\n"
                        f"剩余 {days_left} 天（到期日 {result.get('expires','')}）\n"
                        f"请联系 {admin} 续期",
                        parse_mode="Markdown",
                    )
                elif days_left == 0:
                    await notifier.send(
                        bot,
                        f"🟡 *授权今天到期*\n\n请尽快联系 {admin} 续期",
                    )

            except Exception as e:
                log.debug(f"到期检查异常: {e}")

            # 试用期每小时检查，正式授权每6小时检查
            vr = license_mgr.last_verify_result or {}
            interval = 3600 if vr.get("trial") else 21600
            await _aio.sleep(interval)

    app.post_init = post_init
    log.info("SMS Bot v6 启动")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        write_crash(f"Bot 崩溃: {e}\n{traceback.format_exc()}")
        log.critical(f"Bot 崩溃: {e}", exc_info=True)
        sys.exit(1)

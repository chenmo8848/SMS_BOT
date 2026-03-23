# -*- coding: utf-8 -*-
"""SMS Bot v6 — 监控中心（开关、状态页面）"""

import asyncio
from telegram import Update
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from bot.handlers.common import auth, get_cfg, get_state, get_db, get_pl, get_monitor_svc
from bot.utils.keyboard import kb
from bot.services.phone_link import PhoneLinkManager


def register(app):
    app.add_handler(CommandHandler("monitor", cmd_monitor))
    app.add_handler(CommandHandler("phonelink", cmd_phonelink))
    app.add_handler(CallbackQueryHandler(cb_monitor_menu, pattern=r"^menu_monitor$"))
    app.add_handler(CallbackQueryHandler(cb_mon_on, pattern=r"^cb_mon_on$"))
    app.add_handler(CallbackQueryHandler(cb_mon_off, pattern=r"^cb_mon_off$"))
    app.add_handler(CallbackQueryHandler(cb_phone_menu, pattern=r"^menu_phone$"))
    app.add_handler(CallbackQueryHandler(cb_pl_restart, pattern=r"^cb_pl_restart$"))
    app.add_handler(CallbackQueryHandler(cb_pl_check, pattern=r"^cb_pl_check$"))


async def _render_monitor(q, ctx):
    """渲染监控中心页面"""
    cfg, state = get_cfg(ctx), get_state(ctx)
    db, pl = get_db(ctx), get_pl(ctx)

    loop = asyncio.get_running_loop()
    st = await loop.run_in_executor(None, pl.get_status)

    mon_btn = ("🔴 关闭监控", "cb_mon_off") if state.monitor_active else ("🟢 开启监控", "cb_mon_on")
    mon_st = "🟢 运行中" if state.monitor_active else "🔴 未开启"

    # SIM 信息
    try:
        sims = db.get_sim_cards()
        if sims:
            default_sim = next((s for s in sims if s.is_default), sims[0])
            sim_line = f"💳 {default_sim.name} {default_sim.number}"
        else:
            sim_line = "💳 未检测到 SIM 卡"
    except Exception:
        sim_line = "💳 SIM 读取失败"

    # DB 状态
    db_age = db.get_db_age_seconds()
    if db_age is not None:
        if db_age < 60:
            db_line = f"💾 数据库 ✅ 活跃（{int(db_age)}秒前更新）"
        elif db_age < 300:
            db_line = f"💾 数据库 ✅（{int(db_age//60)}分钟前更新）"
        else:
            db_line = f"💾 数据库 ⚠️ 超过{int(db_age//60)}分钟未更新"
    else:
        db_line = "💾 数据库 ❌ 未找到"

    await q.edit_message_text(
        f"*📡 监控中心*\n━━━━━━━━━━━━━━━\n\n"
        f"🔘 {mon_st}\n"
        f"📱 {PhoneLinkManager.status_text(st)}\n"
        f"{sim_line}\n"
        f"{db_line}\n\n"
        f"_检测频率：连接 {cfg.mon_status_sec}s / 短信 {cfg.mon_sms_sec}s_",
        parse_mode="Markdown",
        reply_markup=kb(
            [mon_btn],
            [("📱 连接详情", "menu_phone"), ("📡 落地测试", "menu_landtest")],
            [("🔙 主菜单", "menu_main")],
        ),
    )


@auth
async def cmd_monitor(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    state = get_state(ctx)
    sub = ctx.args[0].lower() if ctx.args else "status"
    if sub == "on":
        if not state.monitor_active:
            monitor_svc = get_monitor_svc(ctx)
            asyncio.create_task(monitor_svc.run(ctx.application.bot))
        await update.message.reply_text("✅ 监控已开启")
    elif sub == "off":
        state.monitor_active = False
        await update.message.reply_text("⏹ 监控已关闭")
    else:
        st = "🟢 运行中" if state.monitor_active else "🔴 未开启"
        await update.message.reply_text(f"监控状态：{st}\n\n/monitor on 开启\n/monitor off 关闭")


@auth
async def cmd_phonelink(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    pl = get_pl(ctx)
    sub = ctx.args[0].lower() if ctx.args else "check"
    loop = asyncio.get_running_loop()
    if sub == "restart":
        tip = await update.message.reply_text("🔄 重启中...")
        ok = await loop.run_in_executor(None, pl.restart)
        await tip.edit_text("✅ 重启成功" if ok else "❌ 重启失败，请手动打开")
    else:
        tip = await update.message.reply_text("⏳ 检测中...")
        st = await loop.run_in_executor(None, pl.get_status)
        await tip.edit_text(PhoneLinkManager.status_text(st))


async def cb_monitor_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("⏳ 检测中...")
    await _render_monitor(q, ctx)


async def cb_mon_on(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    state = get_state(ctx)
    if not state.monitor_active:
        monitor_svc = get_monitor_svc(ctx)
        asyncio.create_task(monitor_svc.run(ctx.application.bot))
    await q.edit_message_text("⏳ 检测中...")
    await _render_monitor(q, ctx)


async def cb_mon_off(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    get_state(ctx).monitor_active = False
    await q.edit_message_text("⏳ 检测中...")
    await _render_monitor(q, ctx)


async def cb_phone_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    pl = get_pl(ctx)
    await q.edit_message_text("⏳ 检测中...")
    loop = asyncio.get_running_loop()
    st = await loop.run_in_executor(None, pl.get_status)
    await q.edit_message_text(
        f"*📱 手机连接*\n━━━━━━━━━━━━━━━\n\n{PhoneLinkManager.status_text(st)}",
        parse_mode="Markdown",
        reply_markup=kb(
            [("🔄 重启 Phone Link", "cb_pl_restart")],
            [("🔍 重新检测", "cb_pl_check"), ("🔙 返回监控", "menu_monitor")],
        ),
    )


async def cb_pl_restart(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    pl = get_pl(ctx)
    await q.edit_message_text("🔄 重启中，约需30-60秒...")
    loop = asyncio.get_running_loop()
    ok = await loop.run_in_executor(None, pl.restart)
    await q.edit_message_text(
        "✅ 重启成功！" if ok else "❌ 重启失败，请手动检查",
        reply_markup=kb([("🔍 再次检测", "cb_pl_check"), ("🔙 返回监控", "menu_monitor")]),
    )


async def cb_pl_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    pl = get_pl(ctx)
    await q.edit_message_text("⏳ 检测中...")
    loop = asyncio.get_running_loop()
    st = await loop.run_in_executor(None, pl.get_status)
    await q.edit_message_text(
        PhoneLinkManager.status_text(st),
        reply_markup=kb(
            [("🔄 重启", "cb_pl_restart"), ("🔍 再次检测", "cb_pl_check")],
            [("🔙 返回监控", "menu_monitor")],
        ),
    )

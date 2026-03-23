# -*- coding: utf-8 -*-
"""SMS Bot v6 — 落地测试控制"""

import asyncio
from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes
from bot.handlers.common import get_cfg, get_state, get_landtest_svc, get_db
from bot.handlers.menu import back_to_menu
from bot.config import update_config
from bot.utils.keyboard import kb


def register(app):
    app.add_handler(CallbackQueryHandler(cb_landtest_menu, pattern=r"^menu_landtest$"))
    app.add_handler(CallbackQueryHandler(cb_test_toggle, pattern=r"^cb_test_toggle$"))
    app.add_handler(CallbackQueryHandler(cb_test_phone, pattern=r"^set_test_phone$"))
    app.add_handler(CallbackQueryHandler(cb_test_interval, pattern=r"^set_test_interval$"))
    app.add_handler(CallbackQueryHandler(cb_test_content, pattern=r"^set_test_content$"))
    app.add_handler(CallbackQueryHandler(cb_landtest_auto_on, pattern=r"^cb_landtest_auto_on$"))
    app.add_handler(CallbackQueryHandler(cb_landtest_auto_skip, pattern=r"^cb_landtest_auto_skip$"))


async def cb_landtest_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cfg = get_cfg(ctx)
    state = get_state(ctx)
    db = get_db(ctx)

    test_label = "🔴 关闭测试" if state.test_active else "🟢 开启测试"
    phone_str = cfg.test_phone or "未设置"
    try:
        last_body = db.get_last_sent_body()
    except Exception:
        last_body = ""
    content = last_body or cfg.test_content or "（未设置）"
    preview = content[:40] + ("..." if len(content) > 40 else "")
    status = "✅ 运行中" if state.test_active else "⏹ 未开启"

    await q.edit_message_text(
        f"*📡 落地测试*\n━━━━━━━━━━━━━━━\n\n"
        f"🔘 {status}\n"
        f"📞 {phone_str}　⏱ 每 {cfg.test_interval_min} 分钟\n"
        f"💬 {preview}\n\n"
        "_定时发送测试短信验证通道\n"
        "有任务时自动启动，空载自动关闭_",
        parse_mode="Markdown",
        reply_markup=kb(
            [(test_label, "cb_test_toggle")],
            [("📞 号码", "set_test_phone"), ("⏱ 间隔", "set_test_interval"), ("💬 内容", "set_test_content")],
            [("🔙 主菜单", "menu_main")],
        ),
    )


async def cb_test_toggle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cfg = get_cfg(ctx)
    state = get_state(ctx)

    if state.test_active:
        state.test_active = False
        ctx.bot_data["cfg"] = update_config(cfg, test_enabled=False)
        await q.edit_message_text("⏹ 落地测试已关闭",
                                   reply_markup=kb([("🔙 主菜单", "menu_main")]))
    else:
        if not cfg.test_phone:
            await q.answer("请先设置测试号码", show_alert=True)
            return
        svc = get_landtest_svc(ctx)
        asyncio.create_task(svc.run(ctx.application.bot))
        ctx.bot_data["cfg"] = update_config(cfg, test_enabled=True)
        await q.edit_message_text(
            f"✅ 落地测试已开启\n\n"
            f"📞 {cfg.test_phone}\n"
            f"⏱ 每 {cfg.test_interval_min} 分钟\n\n"
            "第一条将在 10 秒内发出",
            reply_markup=kb([("🔙 主菜单", "menu_main")]),
        )


async def cb_test_phone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cfg = get_cfg(ctx)
    await q.edit_message_text(
        f"*设置测试号码*\n\n当前：{cfg.test_phone or '未设置'}\n\n"
        "发送命令修改：\n`/set test_phone 13800000001`",
        parse_mode="Markdown",
        reply_markup=kb([("🔙 返回", "menu_landtest")]),
    )


async def cb_test_interval(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cfg = get_cfg(ctx)
    await q.edit_message_text(
        f"*设置测试间隔*\n\n当前：每 {cfg.test_interval_min} 分钟\n\n"
        "发送命令修改：\n`/set test_interval 30`",
        parse_mode="Markdown",
        reply_markup=kb([("🔙 返回", "menu_landtest")]),
    )


async def cb_test_content(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cfg = get_cfg(ctx)
    await q.edit_message_text(
        f"*设置兜底内容*\n\n当前：{cfg.test_content or '未设置'}\n\n"
        "无发送记录时使用此内容\n`/set test_content 测试内容`",
        parse_mode="Markdown",
        reply_markup=kb([("🔙 返回", "menu_landtest")]),
    )


async def cb_landtest_auto_on(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    state = get_state(ctx)
    cfg = get_cfg(ctx)
    if not state.test_active and cfg.test_phone:
        svc = get_landtest_svc(ctx)
        asyncio.create_task(svc.run(ctx.application.bot))
        await q.edit_message_text(
            f"✅ 落地测试已开启\n📞 {cfg.test_phone}　⏱ 每 {cfg.test_interval_min} 分钟"
        )
    else:
        await q.edit_message_text("📡 落地测试已在运行中")


async def cb_landtest_auto_skip(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("⏭ 已跳过落地测试")

# -*- coding: utf-8 -*-
"""SMS Bot v6 — 发送（/send 单发、/batch 批量、文件上传处理）"""

import asyncio, io
from telegram import Update
from telegram.ext import (CommandHandler, CallbackQueryHandler,
                          MessageHandler, filters, ContextTypes)
from bot.handlers.common import auth, get_cfg, get_state, get_sender, get_notifier
from bot.handlers.menu import back_to_menu
from bot.utils.keyboard import kb
from bot.utils.formatting import calc_eta, mask_phone
from bot.services.excel_parser import parse_batch_text, parse_batch_file


def register(app):
    app.add_handler(CommandHandler("send", cmd_send))
    app.add_handler(CommandHandler("batch", cmd_batch))
    app.add_handler(CallbackQueryHandler(cb_send_menu, pattern=r"^menu_send$"))
    app.add_handler(CallbackQueryHandler(cb_batch_start, pattern=r"^cb_batch_start$"))
    app.add_handler(CallbackQueryHandler(cb_import_confirm, pattern=r"^cb_import_confirm$"))
    app.add_handler(CallbackQueryHandler(cb_import_preview, pattern=r"^cb_import_preview$"))
    app.add_handler(CallbackQueryHandler(cb_import_cancel, pattern=r"^cb_import_cancel"))
    # 文本和文件处理在 data.py 的 handle_upload 中统一处理


@auth
async def cmd_send(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) < 2:
        await update.message.reply_text(
            "*🎯 单发短信*\n\n"
            "用法：`/send 号码 内容`\n\n"
            "示例：\n`/send 13800000001 您好，验证码是1234`",
            parse_mode="Markdown",
        )
        return
    phone = ctx.args[0]
    message = " ".join(ctx.args[1:])
    tip = await update.message.reply_text("⏳ 发送中...")
    sender = get_sender(ctx)
    ok, info = await sender.send(phone, message)
    if ok:
        await tip.edit_text(
            f"✅ 发送成功（{info}）\n📞 {mask_phone(phone)}\n💬 {message[:80]}",
            parse_mode=None,
        )
    else:
        await tip.edit_text(
            f"❌ 发送失败\n📞 {mask_phone(phone)}\n原因：{info}",
            parse_mode=None,
        )


@auth
async def cmd_batch(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*💣 批量导入*\n"
        "━━━━━━━━━━━━━━━\n\n"
        "请发送以下任一格式：\n\n"
        "📋 *粘贴文本*（每行一条）\n"
        "`手机号|短信内容`\n\n"
        "📎 *上传 .txt 文件*\n"
        "格式同上，支持多种编码\n\n"
        "_正在等待您的输入..._",
        parse_mode="Markdown",
        reply_markup=kb([("❌ 取消", "menu_main")]),
    )
    ctx.user_data["waiting_batch"] = True


async def cb_send_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "*📤 发送短信*\n"
        "━━━━━━━━━━━━━━━\n\n"
        "选择发送方式：",
        parse_mode="Markdown",
        reply_markup=kb(
            [("🎯 单发 · 发一条", "cb_send_single_tip")],
            [("📄 文本批量 · 粘贴/上传", "cb_batch_start")],
            [("📊 Excel批量 · 套模板", "cb_data_menu")],
            [("🔙 主菜单", "menu_main")],
        ),
    )


async def cb_batch_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "*💣 批量导入*\n"
        "━━━━━━━━━━━━━━━\n\n"
        "请发送以下任一格式：\n\n"
        "📋 *粘贴文本*（每行一条）\n"
        "`手机号|短信内容`\n\n"
        "📎 *上传 .txt 文件*\n"
        "格式同上\n\n"
        "_正在等待您的输入..._",
        parse_mode="Markdown",
        reply_markup=kb([("❌ 取消", "menu_main")]),
    )
    ctx.user_data["waiting_batch"] = True


async def cb_import_preview(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """确认按钮：先下载 txt，再询问是否发送"""
    q = update.callback_query
    await q.answer()
    txt = ctx.user_data.get("pending_txt")
    tasks_count = len(ctx.user_data.get("pending_tasks", []))
    if not txt:
        await q.edit_message_text("❌ 数据已过期，请重新发送文件")
        return
    cfg = get_cfg(ctx)
    eta = calc_eta(tasks_count, cfg.interval_min, cfg.interval_max)
    await q.message.reply_document(
        document=io.BytesIO(txt.encode("utf-8")),
        filename="sms_tasks.txt",
        caption=f"共 {tasks_count} 条处理好的短信数据",
    )
    await q.edit_message_text(
        f"*数据已返回* ✅\n\n"
        f"共 {tasks_count} 条，预计约 {eta} 分钟\n\n"
        "是否加入发送队列？",
        parse_mode="Markdown",
        reply_markup=kb(
            [("📤 开始发送", "cb_import_confirm")],
            [("🔙 不发送", "cb_import_cancel_after")],
        ),
    )


async def cb_import_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """确认发送：创建任务组并启动"""
    q = update.callback_query
    await q.answer()
    tasks = ctx.user_data.pop("pending_tasks", [])
    ctx.user_data.pop("pending_stats", None)
    ctx.user_data.pop("pending_txt", None)
    if not tasks:
        await q.edit_message_text("❌ 任务已过期，请重新导入")
        return

    state = get_state(ctx)
    cfg = get_cfg(ctx)
    from datetime import datetime
    ts = datetime.now().strftime("%m/%d %H:%M")
    g = state.create_group(f"导入 {ts}", tasks)
    eta = calc_eta(len(tasks), cfg.interval_min, cfg.interval_max)

    if not state.task_running:
        task_mgr = ctx.bot_data["task_mgr"]
        task_mgr.load_group_to_queue(g)
        await back_to_menu(q, ctx,
                           f"▶️ *{g.id} 开始发送*\n📋 {len(tasks)} 条　预计 {eta} 分钟")
        from bot.handlers.task import start_task_runner
        asyncio.create_task(start_task_runner(ctx))
    else:
        await back_to_menu(q, ctx,
                           f"⏳ *{g.id} 已排队*\n📋 {len(tasks)} 条　当前组完成后自动开始")


async def cb_import_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data.pop("pending_tasks", None)
    ctx.user_data.pop("pending_stats", None)
    ctx.user_data.pop("pending_txt", None)
    await back_to_menu(q, ctx, "❌ 已取消")

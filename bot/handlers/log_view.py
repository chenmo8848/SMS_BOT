# -*- coding: utf-8 -*-
"""SMS Bot v6 — 日志查看"""

import io, logging
from datetime import datetime
from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes
from bot.handlers.common import auth, get_cfg
from bot.handlers.menu import back_to_menu
from bot.utils.keyboard import kb
from bot.utils.log_reader import read_log_tail, get_log_bytes, get_log_size, clear_log_file

log = logging.getLogger(__name__)


def register(app):
    app.add_handler(CallbackQueryHandler(cb_log_menu, pattern=r"^menu_log$"))
    app.add_handler(CallbackQueryHandler(cb_log_tail, pattern=r"^cb_log_tail$"))
    app.add_handler(CallbackQueryHandler(cb_log_errors, pattern=r"^cb_log_errors$"))
    app.add_handler(CallbackQueryHandler(cb_log_download, pattern=r"^cb_log_download$"))
    app.add_handler(CallbackQueryHandler(cb_log_clear, pattern=r"^cb_log_clear$"))
    app.add_handler(CallbackQueryHandler(cb_log_clear_confirm, pattern=r"^cb_log_clear_confirm$"))


async def cb_log_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    size = get_log_size()
    await q.edit_message_text(
        f"*📋 运行日志*\n━━━━━━━━━━━━━━━\n\n📁 大小：{size}",
        parse_mode="Markdown",
        reply_markup=kb(
            [("📄 最近30行", "cb_log_tail"), ("⚠️ 仅错误", "cb_log_errors")],
            [("📥 下载", "cb_log_download"), ("🗑 清空", "cb_log_clear")],
            [("🔙 主菜单", "menu_main")],
        ),
    )


async def cb_log_tail(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    tail = read_log_tail(30)
    if len(tail) > 3500:
        tail = "...\n" + tail[-3500:]
    now = datetime.now().strftime("%H:%M:%S")
    await q.edit_message_text(
        f"{tail}\n\n--- {now} ---",
        parse_mode=None,
        reply_markup=kb(
            [("🔄 刷新", "cb_log_tail"), ("⚠️ 仅错误", "cb_log_errors")],
            [("📥 下载", "cb_log_download"), ("🔙 日志菜单", "menu_log")],
        ),
    )


async def cb_log_errors(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    tail = read_log_tail(20, level="ERROR")
    if tail == "（暂无日志）":
        tail = "✅ 没有错误日志"
    elif len(tail) > 3500:
        tail = "...\n" + tail[-3500:]
    now = datetime.now().strftime("%H:%M:%S")
    await q.edit_message_text(
        f"{tail}\n\n--- {now} ---",
        parse_mode=None,
        reply_markup=kb(
            [("🔄 刷新", "cb_log_errors"), ("📄 全部日志", "cb_log_tail")],
            [("📥 下载", "cb_log_download"), ("🔙 日志菜单", "menu_log")],
        ),
    )


async def cb_log_download(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = get_log_bytes()
    ts = datetime.now().strftime("%m%d_%H%M")
    try:
        doc = io.BytesIO(data)
        doc.name = "sms_bot.log"
        await q.message.reply_document(
            document=doc, filename=f"sms_bot_{ts}.log",
            caption=f"完整运行日志（{get_log_size()}）",
        )
    except Exception as e:
        await q.message.reply_text(f"❌ 下载失败：{e}")


async def cb_log_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "⚠️ 确认清空运行日志？\n\n此操作不可恢复",
        reply_markup=kb([("✅ 确认清空", "cb_log_clear_confirm"), ("❌ 取消", "menu_log")]),
    )


async def cb_log_clear_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ok = clear_log_file()
    if ok:
        log.info("日志已被用户清空")
    await back_to_menu(q, ctx, "✅ 日志已清空" if ok else "❌ 清空失败")

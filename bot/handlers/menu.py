# -*- coding: utf-8 -*-
"""SMS Bot v6 — 主菜单（/start、/help、导航回调）"""

import asyncio
from telegram import Update
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from bot.handlers.common import auth, get_cfg, get_state
from bot.utils.keyboard import kb
from bot.utils.formatting import calc_eta, fishing_quote


def register(app):
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CallbackQueryHandler(cb_main, pattern=r"^menu_main$"))
    app.add_handler(CallbackQueryHandler(cb_help, pattern=r"^cb_help$"))


def _build_main_text(cfg, state) -> str:
    mon = "🟢" if state.monitor_active else "🔴"
    ts = state.task_summary()
    lines = ["🎣 *捕鱼达人 v6* 🐟", "━━━━━━━━━━━━━━━━━"]
    if state.global_paused:
        lines.append("⏸ *全局已暂停* — 发送和测试已停")
    lines.append(f"📡 {mon}　⏱ {cfg.interval_min}–{cfg.interval_max}s　🎯 {ts}")
    lines.append("━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def build_main_kb(state):
    """主菜单键盘：4行8按钮，最常用的在前面"""
    ag = state.active_groups()
    task_label = f"📋 任务({len(ag)})" if ag else "📋 任务"
    mon_label = "🟢 监控" if state.monitor_active else "🔴 监控"
    return kb(
        [("📤 发送", "menu_send"),     (task_label, "menu_tasks")],
        [("📊 数据", "cb_data_menu"),  ("📝 模板", "cb_template")],
        [(mon_label, "menu_monitor"),   ("⚙️ 设置", "menu_settings")],
        [("📋 日志", "menu_log"),      ("❓ 帮助", "cb_help")],
    )


@auth
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cfg, state = get_cfg(ctx), get_state(ctx)
    await update.message.reply_text(
        _build_main_text(cfg, state),
        parse_mode="Markdown",
        reply_markup=build_main_kb(state),
    )


@auth
async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*📖 快速上手*\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "① 📝 配置模板 → 设置短信内容格式\n"
        "② 📊 上传数据 → Excel 或文本导入\n"
        "③ 📤 确认发送 → 预览后开炮\n"
        "④ 📡 开启监控 → 自动检测异常\n"
        "⑤ ☕ 坐等收网 → 进度实时推送\n\n"
        "*发送方式*\n"
        "🎯 单发 `/send 号码 内容`\n"
        "💣 批量 `/batch` → 粘贴/上传 txt\n"
        "📦 Excel → 📊 数据处理\n\n"
        "*控制命令*\n"
        "`/pause` 暂停　`/resume` 继续　`/stop` 停止\n"
        "`/resume_tasks` 恢复断电任务\n\n"
        "*监控*\n"
        "三层检测：进程 → DB活跃度 → 窗口卡死\n"
        "收到短信 → 回复通知消息即可回复\n\n"
        "发 /start 回主菜单",
        parse_mode="Markdown",
    )


async def cb_main(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cfg, state = get_cfg(ctx), get_state(ctx)
    await q.edit_message_text(
        _build_main_text(cfg, state),
        parse_mode="Markdown",
        reply_markup=build_main_kb(state),
    )


async def cb_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "*📖 快速上手*\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "① 📝 配置模板 → 设置短信内容格式\n"
        "② 📊 上传数据 → Excel 或文本导入\n"
        "③ 📤 确认发送 → 预览后开炮\n"
        "④ 📡 开启监控 → 自动检测异常\n"
        "⑤ ☕ 坐等收网 → 进度实时推送\n\n"
        "发 /help 查看完整命令",
        parse_mode="Markdown",
        reply_markup=kb([("🔙 主菜单", "menu_main")]),
    )


async def back_to_menu(q, ctx, result_text=""):
    """操作完成后返回主菜单"""
    cfg, state = get_cfg(ctx), get_state(ctx)
    text = (_build_main_text(cfg, state) if not result_text
            else result_text + "\n\n─────────────\n" + _build_main_text(cfg, state))
    try:
        await q.edit_message_text(
            text, parse_mode="Markdown", reply_markup=build_main_kb(state),
        )
    except Exception:
        pass

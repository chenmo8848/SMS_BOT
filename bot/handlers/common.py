# -*- coding: utf-8 -*-
"""SMS Bot v6 — Handler 公共工具（权限检查、服务访问）"""

from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from bot.config import BotConfig
from bot.state import AppState


def auth(func):
    """权限装饰器"""
    @wraps(func)
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        cfg: BotConfig = ctx.bot_data["cfg"]
        uid = update.effective_user.id if update.effective_user else 0
        if uid not in cfg.allowed_user_ids:
            if update.message:
                await update.message.reply_text("⛔ 无权限")
            elif update.callback_query:
                await update.callback_query.answer("⛔ 无权限", show_alert=True)
            return
        # 授权检查（/activate 不拦截）
        state: AppState = ctx.bot_data["state"]
        if state.license_blocked:
            license_mgr = ctx.bot_data.get("license_mgr")
            admin = license_mgr.admin_mention if license_mgr else "管理员"
            if update.message:
                await update.message.reply_text(
                    f"🔒 软件未激活\n\n👉 联系 {admin}\n\n发送 /activate 重新验证授权")
            elif update.callback_query:
                await update.callback_query.answer("🔒 软件未激活", show_alert=True)
            return
        return await func(update, ctx)
    return wrapper


# ─── 从 context 中获取共享对象的便捷函数 ───

def get_cfg(ctx) -> "BotConfig":
    return ctx.bot_data["cfg"]

def get_state(ctx) -> "AppState":
    return ctx.bot_data["state"]

def get_sender(ctx):
    return ctx.bot_data["sender"]

def get_notifier(ctx):
    return ctx.bot_data["notifier"]

def get_db(ctx):
    return ctx.bot_data["db"]

def get_pl(ctx):
    return ctx.bot_data["pl"]

def get_task_mgr(ctx):
    return ctx.bot_data["task_mgr"]

def get_monitor_svc(ctx):
    return ctx.bot_data["monitor_svc"]

def get_landtest_svc(ctx):
    return ctx.bot_data["landtest_svc"]

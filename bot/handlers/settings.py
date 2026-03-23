# -*- coding: utf-8 -*-
"""SMS Bot v6 — 设置（间隔、日期、引擎、SIM、群组通知、重启）"""

import os, re, asyncio, subprocess
from telegram import Update
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from bot.handlers.common import auth, get_cfg, get_state, get_db
from bot.handlers.menu import back_to_menu
from bot.config import update_config, ROOT
from bot.utils.keyboard import kb


def register(app):
    app.add_handler(CommandHandler("set", cmd_set))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("sim", cmd_sim))
    app.add_handler(CommandHandler("restart", cmd_restart))
    app.add_handler(CommandHandler("stop_bot", cmd_stop_bot))
    app.add_handler(CallbackQueryHandler(cb_settings_menu, pattern=r"^menu_settings$"))
    app.add_handler(CallbackQueryHandler(cb_set_detail, pattern=r"^set_"))
    app.add_handler(CallbackQueryHandler(cb_sim, pattern=r"^cb_sim$"))
    app.add_handler(CallbackQueryHandler(cb_engine, pattern=r"^cb_engine_"))
    app.add_handler(CallbackQueryHandler(cb_restart, pattern=r"^cb_restart$"))


@auth
async def cmd_set(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) < 2:
        await update.message.reply_text(
            "*设置说明*\n\n"
            "`/set interval 最小 最大` — 发送间隔(秒)\n"
            "`/set date_sep /` 或 `-` — 日期分隔符\n"
            "`/set mon_status 秒` — 连接检测频率\n"
            "`/set mon_sms 秒` — 短信检测频率\n"
            "`/set group_id ID` — 群组通知(0=关闭)\n"
            "`/set test_phone 号码` — 测试号码\n"
            "`/set test_interval 分钟` — 测试间隔\n"
            "`/set test_content 内容` — 兜底内容",
            parse_mode="Markdown",
        )
        return

    cfg = get_cfg(ctx)
    key = ctx.args[0].lower()
    try:
        if key == "interval" and len(ctx.args) >= 3:
            vmin, vmax = int(ctx.args[1]), int(ctx.args[2])
            if vmin < 5: await update.message.reply_text("❌ 最小5秒"); return
            if vmax < vmin: await update.message.reply_text("❌ 最大值不能小于最小值"); return
            ctx.bot_data["cfg"] = update_config(cfg, interval_min=vmin, interval_max=vmax)
            await update.message.reply_text(f"✅ 发送间隔：{vmin}–{vmax} 秒")
        elif key == "date_sep":
            v = ctx.args[1] if len(ctx.args) > 1 else ""
            if v not in ("/", "-"): await update.message.reply_text("❌ 只支持 / 或 -"); return
            ctx.bot_data["cfg"] = update_config(cfg, sms_date_sep=v)
            await update.message.reply_text(f"✅ 日期分隔符：{v}")
        elif key == "mon_status":
            v = int(ctx.args[1])
            if v < 5: await update.message.reply_text("❌ 最小5秒"); return
            ctx.bot_data["cfg"] = update_config(cfg, mon_status_sec=v)
            await update.message.reply_text(f"✅ 连接检测：每 {v} 秒")
        elif key == "mon_sms":
            v = int(ctx.args[1])
            if v < 3: await update.message.reply_text("❌ 最小3秒"); return
            ctx.bot_data["cfg"] = update_config(cfg, mon_sms_sec=v)
            await update.message.reply_text(f"✅ 短信检测：每 {v} 秒")
        elif key == "group_id":
            v = ctx.args[1].strip()
            gid = None if v == "0" else int(v)
            ctx.bot_data["cfg"] = update_config(cfg, notify_group_id=gid)
            # 同时更新 notifier 的配置引用
            ctx.bot_data["notifier"]._cfg = ctx.bot_data["cfg"]
            await update.message.reply_text("✅ 群组通知已" + ("设置" if gid else "关闭"))
        elif key == "test_phone":
            v = ctx.args[1] if len(ctx.args) > 1 else ""
            if not re.match(r"^1\d{10}$", v): await update.message.reply_text("❌ 请输入11位手机号"); return
            ctx.bot_data["cfg"] = update_config(cfg, test_phone=v)
            await update.message.reply_text(f"✅ 测试号码：{v}")
        elif key == "test_interval":
            v = int(ctx.args[1])
            if v < 1: await update.message.reply_text("❌ 最小1分钟"); return
            ctx.bot_data["cfg"] = update_config(cfg, test_interval_min=v)
            await update.message.reply_text(f"✅ 测试间隔：每 {v} 分钟")
        elif key == "test_content":
            v = " ".join(ctx.args[1:])
            if not v: await update.message.reply_text("❌ 内容不能为空"); return
            ctx.bot_data["cfg"] = update_config(cfg, test_content=v)
            await update.message.reply_text(f"✅ 兜底内容：{v}")
        else:
            await update.message.reply_text(f"❌ 未知参数：{key}")
    except ValueError:
        await update.message.reply_text("❌ 请输入有效数字")


@auth
async def cmd_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cfg = get_cfg(ctx)
    await update.message.reply_text(
        f"*当前设置*\n\n"
        f"⏱ 发送间隔：{cfg.interval_min}–{cfg.interval_max}s\n"
        f"🔧 引擎：{cfg.send_engine}\n"
        f"📡 连接检测：每 {cfg.mon_status_sec}s\n"
        f"💬 短信检测：每 {cfg.mon_sms_sec}s\n"
        f"👥 群组通知：{cfg.notify_group_id or '未设置'}\n"
        f"🌐 代理：{cfg.proxy or '直连'}",
        parse_mode="Markdown",
    )


@auth
async def cmd_sim(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = get_db(ctx)
    cards = db.get_sim_cards()
    if not cards:
        await update.message.reply_text("❌ 找不到 SIM 卡信息"); return
    if not ctx.args:
        lines = [c.display for c in cards]
        tip = "\n\n切换：`/sim <ID>`" if len(cards) > 1 else "\n\n当前只有一张卡"
        await update.message.reply_text("*SIM 卡列表*\n\n" + "\n".join(lines) + tip, parse_mode="Markdown")
        return
    if len(cards) < 2:
        await update.message.reply_text("⚠️ 只有一张卡，无需切换"); return
    try:
        target_id = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("用法：`/sim <ID>`", parse_mode="Markdown"); return
    if target_id not in [c.subscription_id for c in cards]:
        await update.message.reply_text("❌ 找不到该 ID"); return
    ok = db.set_default_sim(target_id)
    card = next(c for c in cards if c.subscription_id == target_id)
    await update.message.reply_text(
        f"{'✅ 已切换' if ok else '❌ 切换失败'}：{card.display}",
    )


@auth
async def cmd_restart(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Bot 正在重启...")
    py = os.path.join(ROOT, "venv", "Scripts", "pythonw.exe")
    if not os.path.exists(py):
        import sys
        py = sys.executable
    subprocess.Popen([py, "-m", "bot"], cwd=ROOT)
    await asyncio.sleep(1)
    os._exit(0)


@auth
async def cmd_stop_bot(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏹ Bot 正在关闭...")
    await asyncio.sleep(1)
    os._exit(0)


async def cb_settings_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cfg = get_cfg(ctx)
    eng_label = {"auto": "自动", "uia": "UIA", "sendkeys": "SendKeys"}.get(cfg.send_engine, cfg.send_engine)
    grp = cfg.notify_group_id or "未开启"
    await q.edit_message_text(
        f"*⚙️ 设置*\n━━━━━━━━━━━━━━━\n\n"
        f"⏱ 发送间隔　{cfg.interval_min}–{cfg.interval_max}s\n"
        f"📅 日期格式　{cfg.sms_date_sep}\n"
        f"🔧 发送引擎　{eng_label}\n"
        f"👥 群组通知　{grp}\n\n"
        f"📡 连接检测　每 {cfg.mon_status_sec}s\n"
        f"💬 短信检测　每 {cfg.mon_sms_sec}s",
        parse_mode="Markdown",
        reply_markup=kb(
            [("⏱ 间隔", "set_interval"), ("📅 日期", "set_date_sep")],
            [("📡 连接频率", "set_mon_status"), ("💬 短信频率", "set_mon_sms")],
            [("👥 群组通知", "set_group_id"), ("💳 SIM卡", "cb_sim")],
            [("🔧 切换引擎", "cb_engine_toggle")],
            [("🔄 重启Bot", "cb_restart"), ("🔙 主菜单", "menu_main")],
        ),
    )


async def cb_set_detail(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cfg = get_cfg(ctx)
    tips = {
        "set_interval":   ("发送间隔", f"当前：{cfg.interval_min}–{cfg.interval_max}s\n\n`/set interval 最小 最大`\n例：`/set interval 30 60`"),
        "set_date_sep":   ("日期分隔符", f"当前：{cfg.sms_date_sep}\n\n`/set date_sep /` 或 `/set date_sep -`"),
        "set_mon_status": ("连接检测频率", f"当前：每 {cfg.mon_status_sec}s\n\n`/set mon_status 秒数`"),
        "set_mon_sms":    ("短信检测频率", f"当前：每 {cfg.mon_sms_sec}s\n\n`/set mon_sms 秒数`"),
        "set_group_id":   ("群组通知", f"当前：{cfg.notify_group_id or '未设置'}\n\n`/set group_id 群组ID`\n关闭：`/set group_id 0`"),
    }
    key = q.data
    if key not in tips:
        return
    title, tip = tips[key]
    await q.edit_message_text(f"*{title}*\n\n{tip}", parse_mode="Markdown",
                               reply_markup=kb([("🔙 返回设置", "menu_settings")]))


async def cb_sim(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    db = get_db(ctx)
    cards = db.get_sim_cards()
    if not cards:
        await q.edit_message_text("*SIM 卡*\n\n❌ 未检测到 SIM 卡", parse_mode="Markdown",
                                   reply_markup=kb([("🔙 返回设置", "menu_settings")]))
        return
    lines = []
    for c in cards:
        mark = "✅" if c.is_default else "☐"
        lines.append(f"{mark} *卡{c.sim_slot_index+1}*  ID:`{c.subscription_id}`\n　{c.name} · `{c.number}`")
    tip = "\n\n切换：`/sim <ID>`" if len(cards) > 1 else "\n\n当前只有一张卡"
    await q.edit_message_text(
        "*💳 SIM 卡*\n━━━━━━━━━━━━━━━\n\n" + "\n\n".join(lines) + tip,
        parse_mode="Markdown",
        reply_markup=kb([("🔙 返回设置", "menu_settings")]),
    )


async def cb_engine(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cfg = get_cfg(ctx)
    # 循环切换：auto → uia → sendkeys → auto
    cycle = {"auto": "uia", "uia": "sendkeys", "sendkeys": "auto"}
    new_engine = cycle.get(cfg.send_engine, "auto")
    ctx.bot_data["cfg"] = update_config(cfg, send_engine=new_engine)
    # 清除 auto 缓存
    get_state(ctx).engine_resolved = None
    label = {"auto": "自动模式", "uia": "UIA 精确模式", "sendkeys": "SendKeys 兼容模式"}[new_engine]
    await back_to_menu(q, ctx, f"🔧 已切换为 {label}")


async def cb_restart(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("🔄 Bot 正在重启...")
    py = os.path.join(ROOT, "venv", "Scripts", "pythonw.exe")
    if not os.path.exists(py):
        import sys
        py = sys.executable
    subprocess.Popen([py, "-m", "bot"], cwd=ROOT)
    await asyncio.sleep(1)
    os._exit(0)

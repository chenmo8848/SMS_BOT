# -*- coding: utf-8 -*-
"""SMS Bot v6 — 任务管理（列表、暂停/继续/停止、全局暂停、任务执行器）"""

import asyncio, random, io, logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from bot.handlers.common import (auth, get_cfg, get_state, get_sender,
                                  get_notifier, get_task_mgr)
from bot.handlers.menu import back_to_menu, build_main_kb
from bot.utils.keyboard import kb, kb_rows
from bot.utils.formatting import calc_eta, mask_phone
from bot.models.task import GroupState

log = logging.getLogger(__name__)


def register(app):
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("pause", cmd_pause))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("resume_tasks", cmd_resume_tasks))
    app.add_handler(CommandHandler("clear_tasks", cmd_clear_tasks))
    app.add_handler(CallbackQueryHandler(cb_tasks_menu, pattern=r"^menu_tasks$"))
    app.add_handler(CallbackQueryHandler(cb_task_detail, pattern=r"^tg_detail_"))
    app.add_handler(CallbackQueryHandler(cb_task_pause, pattern=r"^tg_pause_"))
    app.add_handler(CallbackQueryHandler(cb_task_resume, pattern=r"^tg_resume_"))
    app.add_handler(CallbackQueryHandler(cb_task_stop, pattern=r"^tg_stop_"))
    app.add_handler(CallbackQueryHandler(cb_pause_all, pattern=r"^cb_pause_all$"))
    app.add_handler(CallbackQueryHandler(cb_stop_all, pattern=r"^cb_stop_all$"))
    app.add_handler(CallbackQueryHandler(cb_stop_confirm, pattern=r"^cb_stop_confirm$"))
    app.add_handler(CallbackQueryHandler(cb_global_pause, pattern=r"^cb_global_pause$"))
    app.add_handler(CallbackQueryHandler(cb_global_resume, pattern=r"^cb_global_resume$"))
    app.add_handler(CallbackQueryHandler(cb_resume_btn, pattern=r"^cb_resume$"))


# ─── 命令 ───

@auth
async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    state = get_state(ctx)
    ag = state.active_groups()
    if not ag:
        await update.message.reply_text("📭 当前没有任务")
        return
    cfg = get_cfg(ctx)
    lines = []
    for g in ag:
        lines.append(f"{g.state_icon} *{g.id}* {g.name}　✅{g.sent} ❌{g.failed} ⏳{g.remaining}/{g.total}")
    total_r = sum(g.remaining for g in ag)
    await update.message.reply_text(
        "*📊 任务状态*\n\n" + "\n".join(lines) +
        f"\n\n预计还需 {calc_eta(total_r, cfg.interval_min, cfg.interval_max)} 分钟",
        parse_mode="Markdown",
    )


@auth
async def cmd_pause(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    state = get_state(ctx)
    if not state.task_running:
        await update.message.reply_text("📭 没有运行中的任务"); return
    if state.task_paused:
        await update.message.reply_text("⏸ 任务已在暂停中",
                                         reply_markup=kb([("▶️ 继续", "cb_resume")])); return
    state.task_paused = True
    await update.message.reply_text(
        f"⏸ *任务已暂停*\n剩余 {len(state.task_queue)} 条待发",
        parse_mode="Markdown",
        reply_markup=kb([("▶️ 继续", "cb_resume"), ("⏹ 停止", "cb_stop_confirm")]),
    )


@auth
async def cmd_resume(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    state = get_state(ctx)
    if not state.task_running:
        await update.message.reply_text("📭 没有运行中的任务"); return
    state.task_paused = False
    await update.message.reply_text(
        f"▶️ *任务已继续*\n剩余 {len(state.task_queue)} 条待发",
        parse_mode="Markdown",
    )


@auth
async def cmd_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    state = get_state(ctx)
    if not state.task_running:
        await update.message.reply_text("📭 没有运行中的任务"); return
    await update.message.reply_text(
        f"⏹ 确认停止任务？剩余 {len(state.task_queue)} 条",
        reply_markup=kb([("✅ 确认停止", "cb_stop_confirm"), ("❌ 取消", "menu_main")]),
    )


@auth
async def cmd_resume_tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    state = get_state(ctx)
    task_mgr = get_task_mgr(ctx)
    if state.task_running:
        await update.message.reply_text("⚠️ 已有任务运行中"); return
    paused = [g for g in state.task_groups if g.state == GroupState.PAUSED and g.queue]
    if not paused:
        await update.message.reply_text("📭 没有待恢复任务"); return
    for g in paused:
        g.state = GroupState.QUEUED
    task_mgr.load_group_to_queue(paused[0])
    cfg = get_cfg(ctx)
    total = sum(g.remaining for g in paused)
    await update.message.reply_text(
        f"▶️ *恢复 {len(paused)} 组任务*\n\n"
        f"共 {total} 条待发\n预计 {calc_eta(total, cfg.interval_min, cfg.interval_max)} 分钟",
        parse_mode="Markdown",
    )
    asyncio.create_task(start_task_runner(ctx))


@auth
async def cmd_clear_tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    state = get_state(ctx)
    task_mgr = get_task_mgr(ctx)
    if state.task_running:
        await update.message.reply_text("⚠️ 任务运行中，请先 /stop"); return
    state.task_queue.clear()
    state.task_groups.clear()
    task_mgr.clear()
    state.task_stats.update({"total": 0, "sent": 0, "failed": 0, "start_time": None})
    await update.message.reply_text("✅ 所有任务已清除")


# ─── 回调 ───

async def cb_tasks_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    state = get_state(ctx)
    ag = state.active_groups()
    if not ag:
        await q.edit_message_text(
            "*📋 任务中心*\n━━━━━━━━━━━━━━━\n\n暂无任务",
            parse_mode="Markdown",
            reply_markup=kb(
                [("📤 发送", "menu_send"), ("📊 数据", "cb_data_menu")],
                [("🔙 主菜单", "menu_main")],
            ),
        )
        return

    lines = []
    btns = []
    for g in ag:
        lines.append(
            f"{g.state_icon} *{g.id}* · {g.name}\n"
            f"　　{g.progress_bar} {g.progress_pct}%\n"
            f"　　✅ {g.sent}　❌ {g.failed}　⏳ {g.remaining}/{g.total}"
        )
        btns.append([(f"{g.state_icon} {g.id} 详情", f"tg_detail_{g.id}")])

    # 全局暂停/恢复按钮
    if state.global_paused:
        btns.append([("▶️ 恢复发送", "cb_global_resume")])
    else:
        btns.append([("⏸ 暂停发送", "cb_global_pause")])
    btns.append([("⏸ 全部暂停", "cb_pause_all"), ("⏹ 全部停止", "cb_stop_all")])
    btns.append([("🔙 主菜单", "menu_main")])

    await q.edit_message_text(
        "*📋 任务中心*\n━━━━━━━━━━━━━━━\n\n" + "\n\n".join(lines),
        parse_mode="Markdown",
        reply_markup=kb_rows(btns),
    )


async def cb_task_detail(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    gid = q.data[len("tg_detail_"):]
    state = get_state(ctx)
    cfg = get_cfg(ctx)
    g = state.get_group(gid)
    if not g:
        await q.edit_message_text("❌ 任务组不存在"); return
    eta = calc_eta(g.remaining, cfg.interval_min, cfg.interval_max)
    text = (
        f"*🎯 {g.id}*\n━━━━━━━━━━━━━━━\n\n"
        f"📌 {g.name}\n🔘 {g.state_icon} {g.state_text}\n\n"
        f"{g.progress_bar} {g.progress_pct}%\n\n"
        f"✅ {g.sent}　❌ {g.failed}　⏳ {g.remaining}　📦 {g.total}\n"
        f"🕐 预计 {eta} 分钟"
    )
    btns = []
    if g.state == GroupState.RUNNING:
        btns.append([("⏸ 暂停", f"tg_pause_{gid}"), ("⏹ 停止", f"tg_stop_{gid}")])
    elif g.state == GroupState.PAUSED:
        btns.append([("▶️ 继续", f"tg_resume_{gid}"), ("⏹ 停止", f"tg_stop_{gid}")])
    elif g.state == GroupState.QUEUED:
        btns.append([("⏹ 取消", f"tg_stop_{gid}")])
    btns.append([("🔙 任务列表", "menu_tasks")])
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb_rows(btns))


async def cb_task_pause(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    gid = q.data[len("tg_pause_"):]
    state = get_state(ctx)
    task_mgr = get_task_mgr(ctx)
    g = state.get_group(gid)
    if g and g.state == GroupState.RUNNING:
        state.task_paused = True
        task_mgr.sync_group_from_queue(g)
        g.state = GroupState.PAUSED
    elif g:
        g.state = GroupState.PAUSED
    await q.edit_message_text(f"⏸ *{gid} 已暂停*", parse_mode="Markdown",
                               reply_markup=kb([("🔙 任务列表", "menu_tasks")]))


async def cb_task_resume(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    gid = q.data[len("tg_resume_"):]
    state = get_state(ctx)
    task_mgr = get_task_mgr(ctx)
    g = state.get_group(gid)
    if g:
        if not state.task_running:
            g.state = GroupState.RUNNING
            task_mgr.load_group_to_queue(g)
            asyncio.create_task(start_task_runner(ctx))
        elif state.current_group() is None:
            g.state = GroupState.RUNNING
            task_mgr.load_group_to_queue(g)
            state.task_paused = False
        else:
            g.state = GroupState.QUEUED
    await q.edit_message_text(f"▶️ *{gid} 已恢复*", parse_mode="Markdown",
                               reply_markup=kb([("🔙 任务列表", "menu_tasks")]))


async def cb_task_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    gid = q.data[len("tg_stop_"):]
    state = get_state(ctx)
    g = state.get_group(gid)
    if g:
        was_running = g.state == GroupState.RUNNING
        g.state = GroupState.STOPPED
        if was_running:
            state.task_running = False
    await q.edit_message_text(f"⏹ *{gid} 已停止*", parse_mode="Markdown",
                               reply_markup=kb([("🔙 任务列表", "menu_tasks")]))


async def cb_pause_all(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    state = get_state(ctx)
    task_mgr = get_task_mgr(ctx)
    for g in state.active_groups():
        if g.state == GroupState.RUNNING:
            state.task_paused = True
            task_mgr.sync_group_from_queue(g)
        g.state = GroupState.PAUSED
    await back_to_menu(q, ctx, "⏸ 全部任务已暂停")


async def cb_stop_all(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    state = get_state(ctx)
    for g in state.active_groups():
        g.state = GroupState.STOPPED
    state.task_running = False
    state.task_paused = False
    await back_to_menu(q, ctx, "⏹ 全部任务已停止")


async def cb_stop_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    state = get_state(ctx)
    for g in state.active_groups():
        g.state = GroupState.STOPPED
    state.task_running = False
    state.task_paused = False
    await back_to_menu(q, ctx, "⏹ *全部任务已停止*")


async def cb_global_pause(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    state = get_state(ctx)
    state.global_paused = True
    log.info("全局暂停")
    await back_to_menu(q, ctx, "⏸ 已暂停所有发送\n监控和短信通知不受影响")


async def cb_global_resume(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    state = get_state(ctx)
    state.global_paused = False
    log.info("全局恢复")
    await back_to_menu(q, ctx, "▶️ 已恢复发送")


async def cb_resume_btn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    state = get_state(ctx)
    state.task_paused = False
    await back_to_menu(q, ctx, "▶️ *任务已恢复*")


# ═══════════════════════════════════════════════════════
#  任务执行器（核心循环）
# ═══════════════════════════════════════════════════════

async def start_task_runner(ctx: ContextTypes.DEFAULT_TYPE):
    """安全包装的任务执行器入口"""
    state = get_state(ctx)
    cfg = get_cfg(ctx)
    sender = get_sender(ctx)
    notifier = get_notifier(ctx)
    task_mgr = get_task_mgr(ctx)
    bot = ctx.application.bot

    # 落地测试提示
    if cfg.test_enabled and cfg.test_phone and not state.test_active:
        await notifier.send_to_user(
            bot,
            f"📡 *是否开启落地测试？*\n\n"
            f"📞 {cfg.test_phone}　⏱ 每 {cfg.test_interval_min} 分钟",
        )
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        await bot.send_message(
            chat_id=cfg.notify_user_id, text="选择 👇",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ 开启", callback_data="cb_landtest_auto_on"),
                InlineKeyboardButton("⏭ 跳过", callback_data="cb_landtest_auto_skip"),
            ]]),
        )

    try:
        await _run_task_queue(bot, cfg, state, sender, notifier, task_mgr)
    except Exception as e:
        state.task_running = False
        state.task_paused = False
        cg = state.current_group()
        if cg:
            task_mgr.sync_group_from_queue(cg)
            cg.state = GroupState.PAUSED
        log.error(f"任务执行器异常: {e}", exc_info=True)
        task_mgr.save()
        await notifier.send(
            bot,
            "❌ *任务异常终止*\n\n"
            f"错误：{str(e)[:200]}\n\n"
            "任务已保存，发送 /resume_tasks 继续",
        )


async def _run_task_queue(bot, cfg, state, sender, notifier, task_mgr):
    """多组任务执行器"""
    state.task_running = True

    while True:
        cg = state.current_group()
        if not cg:
            nxt = state.pick_next_group()
            if not nxt:
                break
            task_mgr.load_group_to_queue(nxt)
            cg = nxt
            await notifier.send(
                bot,
                f"🚀 *{cg.id} 开炮！*\n\n"
                f"📌 {cg.name}\n"
                f"💣 弹药 {cg.total} 发　⏱ 预计 {calc_eta(cg.total, cfg.interval_min, cfg.interval_max)} 分钟",
            )

        state.task_paused = False
        results = []
        consecutive_fail = 0

        while True:
            # 暂停处理
            if state.task_paused:
                task_mgr.sync_group_from_queue(cg)
                cg.state = GroupState.PAUSED
                task_mgr.save()
                await asyncio.sleep(1)
                if not state.task_running:
                    break
                if cg.state == GroupState.RUNNING:
                    state.task_paused = False
                    task_mgr.load_group_to_queue(cg)
                elif cg.state == GroupState.STOPPED:
                    break
                continue

            # 优先级等待（落地测试/短信回复）
            while state.priority_held and state.task_running:
                await asyncio.sleep(0.5)
            while state.global_paused and state.task_running and not state.task_paused:
                await asyncio.sleep(1)

            if not state.task_queue or not state.task_running:
                break
            task = state.task_queue.popleft()

            ok, info = await sender.send(task.phone, task.message)

            if ok:
                state.task_stats["sent"] += 1
                consecutive_fail = 0
            else:
                state.task_stats["failed"] += 1
                consecutive_fail += 1

            cg.sent = state.task_stats["sent"]
            cg.failed = state.task_stats["failed"]
            cg.queue = state.task_queue.copy()

            results.append(("✅ " if ok else "❌ ") + mask_phone(task.phone) +
                           ("" if ok else " — " + info))
            task_mgr.save()

            # 失败通知
            if not ok:
                await notifier.send(
                    bot,
                    f"❌ 发送失败 · {mask_phone(task.phone)} · {info}\n"
                    f"任务 {cg.id}　{cg.done}/{cg.total}",
                    parse_mode=None,
                )
                if consecutive_fail >= 3:
                    state.task_paused = True
                    cg.state = GroupState.PAUSED
                    task_mgr.sync_group_from_queue(cg)
                    task_mgr.save()
                    await notifier.send(
                        bot,
                        f"⚠️ *{cg.id} 连续 {consecutive_fail} 次失败，已自动暂停*\n\n"
                        "请检查手机连接，确认后发 /resume 继续",
                    )
                    consecutive_fail = 0

            # 每 10 条进度通知
            if cg.done > 0 and cg.done % 10 == 0:
                await notifier.send(
                    bot,
                    f"📊 {cg.id} 进度 {cg.done}/{cg.total} ({cg.progress_pct}%)\n"
                    f"✅ {cg.sent}　❌ {cg.failed}",
                    parse_mode=None,
                )

            if not state.task_queue:
                break

            # 随机间隔
            interval = random.randint(cfg.interval_min, cfg.interval_max)
            for _ in range(interval):
                await asyncio.sleep(1)
                if not state.task_running or state.task_paused or state.priority_held or state.global_paused:
                    break
            while state.priority_held and state.task_running:
                await asyncio.sleep(1)
            while state.global_paused and state.task_running and not state.task_paused:
                await asyncio.sleep(1)

        # 当前组结束处理
        task_mgr.sync_group_from_queue(cg)

        if cg.state == GroupState.STOPPED or not state.task_running:
            if cg.state != GroupState.STOPPED:
                cg.state = GroupState.STOPPED
            if cg.remaining:
                await notifier.send(bot, f"⏹ *{cg.id} 收杆*\n\n剩余 {cg.remaining} 发已保存")
        elif not cg.queue:
            cg.state = GroupState.COMPLETED
            elapsed = int((datetime.now() - (state.task_stats.get("start_time") or datetime.now())).total_seconds() / 60)
            verdict = ("🏆 全部成功！" if cg.progress_pct >= 100
                       else "✅ 基本成功" if cg.progress_pct >= 95
                       else "⚠️ 部分失败" if cg.progress_pct >= 50
                       else "❌ 大量失败，请检查连接")
            await notifier.send(
                bot,
                f"✅ *{cg.id} 完成* · {cg.sent}/{cg.total} 成功"
                f"（{cg.progress_pct}%）· {elapsed}分钟\n{verdict}",
            )
            if results and len(results) > 15:
                try:
                    doc = io.BytesIO("\n".join(results).encode("utf-8"))
                    doc.name = "results.txt"
                    await bot.send_document(chat_id=cfg.notify_user_id, document=doc,
                                            caption=f"{cg.id} 发送明细")
                except Exception:
                    pass

        if not state.task_running:
            break

    state.task_running = False
    state.task_paused = False
    task_mgr.clear()
    log.info("任务执行器退出")

    # 任务清空 → 关闭落地测试
    if state.test_active:
        state.test_active = False
        log.info("落地测试：任务已清空，自动关闭")
        try:
            await notifier.send(bot, "📡 落地测试已自动关闭（无任务）", parse_mode=None)
        except Exception:
            pass

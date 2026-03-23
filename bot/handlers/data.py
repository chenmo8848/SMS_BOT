# -*- coding: utf-8 -*-
"""SMS Bot v6 — 数据处理（上传文件 → 选择处理方式：短信装弹 or 数据整理）"""

import io
from datetime import datetime
from telegram import Update
from telegram.ext import (CommandHandler, CallbackQueryHandler,
                          MessageHandler, filters, ContextTypes)
from bot.handlers.common import auth, get_cfg, get_state
from bot.handlers.menu import back_to_menu
from bot.utils.keyboard import kb
from bot.utils.formatting import calc_eta
from bot.services.excel_parser import (
    parse_excel_for_sms, parse_excel_for_user,
    parse_batch_text, parse_batch_file,
)


def register(app):
    app.add_handler(CallbackQueryHandler(cb_data_menu, pattern=r"^cb_data_menu$"))
    app.add_handler(CallbackQueryHandler(cb_process_as_sms, pattern=r"^cb_process_sms$"))
    app.add_handler(CallbackQueryHandler(cb_process_as_user, pattern=r"^cb_process_user$"))
    app.add_handler(CallbackQueryHandler(cb_user_cols_edit, pattern=r"^cb_user_cols_edit$"))
    app.add_handler(CallbackQueryHandler(cb_user_cols_confirm, pattern=r"^cb_user_cols_confirm$"))
    app.add_handler(CallbackQueryHandler(cb_udata_excel, pattern=r"^cb_udata_excel$"))
    app.add_handler(CallbackQueryHandler(cb_udata_txt, pattern=r"^cb_udata_txt$"))
    app.add_handler(CallbackQueryHandler(cb_uimport_datetime, pattern=r"^cb_uimport_use_datetime$"))
    app.add_handler(CallbackQueryHandler(cb_uimport_keep, pattern=r"^cb_uimport_keep_fmt$"))
    # 文本和文件统一入口
    app.add_handler(MessageHandler(filters.Document.ALL & ~filters.COMMAND, handle_upload))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))


async def cb_data_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "*📊 数据处理*\n━━━━━━━━━━━━━━━\n\n"
        "直接上传 Excel 文件\n"
        "Bot 接收后选择处理方式：\n\n"
        "📨 *短信装弹* — 套模板生成发送任务\n"
        "👥 *数据整理* — 按列整理导出文件\n\n"
        "👇 现在就发送 .xlsx 文件给我",
        parse_mode="Markdown",
        reply_markup=kb([("🔙 主菜单", "menu_main")]),
    )
    ctx.user_data["waiting_data"] = True


# ─── 文件上传统一处理 ───

@auth
async def handle_upload(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """统一文件上传入口"""
    if update.effective_user.id not in get_cfg(ctx).allowed_user_ids:
        return
    fname = (update.message.document.file_name or "").lower()

    # txt 文件：批量导入模式
    if fname.endswith(".txt") and ctx.user_data.get("waiting_batch"):
        ctx.user_data["waiting_batch"] = False
        await _handle_batch_txt(update, ctx)
        return

    # xlsx 文件
    if fname.endswith(".xlsx") or fname.endswith(".xls"):
        # 下载并缓存文件
        tip = await update.message.reply_text("⏳ 正在读取文件...")
        try:
            file = await update.message.document.get_file()
            data = bytes(await file.download_as_bytearray())
            ctx.user_data["pending_excel_data"] = data
            ctx.user_data["pending_excel_fname"] = fname

            # 如果在数据处理页面或没有特定模式 → 让用户选择
            if ctx.user_data.get("waiting_data") or not (
                ctx.user_data.get("waiting_import") or ctx.user_data.get("waiting_user_import")
            ):
                ctx.user_data.pop("waiting_data", None)
                await tip.edit_text(
                    f"✅ 已接收 {update.message.document.file_name}\n\n"
                    "选择处理方式：",
                    reply_markup=kb(
                        [("📨 生成短信", "cb_process_sms")],
                        [("👥 整理数据", "cb_process_user")],
                        [("❌ 取消", "menu_main")],
                    ),
                )
                return

            # 短信装弹模式
            if ctx.user_data.get("waiting_import"):
                ctx.user_data["waiting_import"] = False
                await tip.delete()
                await _process_as_sms(update.message, ctx, data)
                return

            # 数据整理模式
            if ctx.user_data.get("waiting_user_import"):
                ctx.user_data["waiting_user_import"] = False
                await tip.delete()
                await _process_as_user(update.message, ctx, data)
                return

        except Exception as e:
            await tip.edit_text(f"❌ 文件读取失败：{e}")
        return

    # 不支持的格式
    if ctx.user_data.get("waiting_import") or ctx.user_data.get("waiting_data"):
        await update.message.reply_text("❌ 请发送 .xlsx 格式的 Excel 文件")
        ctx.user_data.pop("waiting_import", None)
        ctx.user_data.pop("waiting_data", None)


# ─── 选择处理方式的回调 ───

async def cb_process_as_sms(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = ctx.user_data.pop("pending_excel_data", None)
    if not data:
        await q.edit_message_text("❌ 文件已过期，请重新上传")
        return
    await q.edit_message_text("⏳ 正在解析...")
    await _process_as_sms(q.message, ctx, data)


async def cb_process_as_user(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = ctx.user_data.get("pending_excel_data")
    if not data:
        await q.edit_message_text("❌ 文件已过期，请重新上传")
        return
    await q.edit_message_text("⏳ 正在处理...")
    await _process_as_user(q.message, ctx, data)


# ─── 短信装弹处理 ───

async def _process_as_sms(msg, ctx, data: bytes):
    state = get_state(ctx)
    cfg = get_cfg(ctx)

    if state.task_running:
        await msg.reply_text("⚠️ 当前有任务运行中，请先 /stop 再导入")
        return

    result = parse_excel_for_sms(data, state.sms_template, cfg.sms_date_sep)

    if result.errors and not result.tasks:
        await msg.reply_text("❌ " + "\n".join(result.errors[:10]))
        return
    if not result.tasks:
        await msg.reply_text("❌ 没有有效数据")
        return

    eta = calc_eta(result.count, cfg.interval_min, cfg.interval_max)
    max_a = int(max(result.amounts)) if result.amounts else 0
    min_a = int(min(result.amounts)) if result.amounts else 0
    avg_a = int(sum(result.amounts) / len(result.amounts)) if result.amounts else 0

    preview = "\n\n".join(result.preview_lines)
    if result.count > 3:
        preview += f"\n\n_...还有 {result.count - 3} 条_"

    err_text = f"\n⚠️ 跳过 {len(result.errors)} 行" if result.errors else ""

    ctx.user_data["pending_tasks"] = result.tasks
    ctx.user_data["pending_txt"] = result.txt_content

    await msg.reply_text(
        f"*📊 解析完成*\n\n"
        f"📋 共 {result.count} 条{err_text}\n"
        f"🔝 最高：{max_a:,} 斤　🔻 最低：{min_a:,} 斤\n"
        f"📊 平均：{avg_a:,} 斤　⏱ 预计 {eta} 分钟\n\n"
        f"*前3条预览：*\n\n{preview}\n\n"
        "请确认数据无误",
        parse_mode="Markdown",
        reply_markup=kb(
            [("✅ 确认", "cb_import_preview"), ("❌ 取消", "cb_import_cancel")],
        ),
    )


# ─── 数据整理处理 ───

async def _process_as_user(msg, ctx, data: bytes):
    cfg = get_cfg(ctx)
    result = parse_excel_for_user(data, cfg.user_import_cols, cfg.user_date_fmt)

    if result.error:
        await msg.reply_text(f"❌ {result.error}")
        return

    # 检测到时分秒但格式不含
    fmt_has_time = any(x in cfg.user_date_fmt for x in ["%H", "%M", "%S"])
    if result.has_time_data and not fmt_has_time:
        ctx.user_data["pending_user_data"] = data
        await msg.reply_text(
            "⚠️ 检测到日期含时分秒\n\n"
            f"当前格式：{cfg.user_date_fmt}（不含时间）\n\n"
            "是否改为含时分秒？",
            reply_markup=kb(
                [("✅ 改为 %Y-%m-%d %H:%M:%S", "cb_uimport_use_datetime")],
                [("⏭ 保持当前格式", "cb_uimport_keep_fmt")],
            ),
        )
        return

    await _send_user_result(msg, ctx, result)


async def _send_user_result(msg, ctx, result):
    skip_report = ""
    if result.skip_rows:
        skip_msg = "\n".join(result.skip_rows[:20])
        if len(result.skip_rows) > 20:
            skip_msg += f"\n...共 {len(result.skip_rows)} 行"
        skip_report = f"\n\n⚠️ 跳过 {len(result.skip_rows)} 行：\n{skip_msg}"

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ctx.user_data["pending_udata_xlsx"] = result.xlsx_bytes
    ctx.user_data["pending_udata_txt"] = result.txt_bytes
    ctx.user_data["pending_udata_ts"] = ts
    ctx.user_data["pending_udata_added"] = result.count

    await msg.reply_text(
        f"✅ 处理完成，共 {result.count} 条{skip_report}\n\n选择输出格式：",
        reply_markup=kb([("📊 Excel", "cb_udata_excel"), ("📄 TXT", "cb_udata_txt")]),
    )


async def cb_uimport_datetime(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    from bot.config import update_config
    cfg = get_cfg(ctx)
    ctx.bot_data["cfg"] = update_config(cfg, user_date_fmt="%Y-%m-%d %H:%M:%S")
    data = ctx.user_data.pop("pending_user_data", None)
    if not data:
        await q.edit_message_text("❌ 数据已过期"); return
    await q.edit_message_text("✅ 格式已更新，继续处理...")
    result = parse_excel_for_user(data, ctx.bot_data["cfg"].user_import_cols, "%Y-%m-%d %H:%M:%S")
    if result.error:
        await q.message.reply_text(f"❌ {result.error}"); return
    await _send_user_result(q.message, ctx, result)


async def cb_uimport_keep(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = ctx.user_data.pop("pending_user_data", None)
    if not data:
        await q.edit_message_text("❌ 数据已过期"); return
    await q.edit_message_text("⏳ 继续处理...")
    cfg = get_cfg(ctx)
    result = parse_excel_for_user(data, cfg.user_import_cols, cfg.user_date_fmt)
    if result.error:
        await q.message.reply_text(f"❌ {result.error}"); return
    await _send_user_result(q.message, ctx, result)


async def cb_udata_excel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    xlsx = ctx.user_data.pop("pending_udata_xlsx", None)
    ts = ctx.user_data.pop("pending_udata_ts", "")
    added = ctx.user_data.pop("pending_udata_added", 0)
    ctx.user_data.pop("pending_udata_txt", None)
    if not xlsx:
        await q.edit_message_text("❌ 数据已过期"); return
    fname = f"用户数据_{ts}.xlsx"
    await q.message.reply_document(document=io.BytesIO(xlsx), filename=fname, caption=f"共 {added} 条")
    await back_to_menu(q, ctx, f"✅ 已发送 {fname}")


async def cb_udata_txt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    txt = ctx.user_data.pop("pending_udata_txt", None)
    ts = ctx.user_data.pop("pending_udata_ts", "")
    added = ctx.user_data.pop("pending_udata_added", 0)
    ctx.user_data.pop("pending_udata_xlsx", None)
    if not txt:
        await q.edit_message_text("❌ 数据已过期"); return
    fname = f"用户数据_{ts}.txt"
    await q.message.reply_document(document=io.BytesIO(txt), filename=fname, caption=f"共 {added} 条")
    await back_to_menu(q, ctx, f"✅ 已发送 {fname}")


async def cb_user_cols_edit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cfg = get_cfg(ctx)
    await q.edit_message_text(
        f"修改列配置\n\n"
        f"当前列：{'、'.join(cfg.user_import_cols)}\n"
        f"日期格式：{cfg.user_date_fmt}\n\n"
        "发送新配置（两行）：\n"
        "第一行：列名，逗号分隔\n"
        "第二行（可选）：日期格式\n\n"
        "%Y=年 %m=月 %d=日 %H=时 %M=分 %S=秒",
        reply_markup=kb([("🔙 取消", "cb_data_menu")]),
    )
    ctx.user_data["waiting_user_cols"] = True


async def cb_user_cols_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    new_cols = ctx.user_data.pop("pending_user_cols", None)
    new_fmt = ctx.user_data.pop("pending_date_fmt", None)
    if not new_cols:
        await q.edit_message_text("❌ 已过期"); return
    from bot.config import update_config
    cfg = get_cfg(ctx)
    kwargs = {"user_import_cols": new_cols}
    if new_fmt:
        kwargs["user_date_fmt"] = new_fmt
    ctx.bot_data["cfg"] = update_config(cfg, **kwargs)
    await q.edit_message_text(f"✅ 配置已更新\n\n列：{'、'.join(new_cols)}")


# ─── 文本消息处理 ───

@auth
async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """统一文本消息入口"""
    if update.effective_user.id not in get_cfg(ctx).allowed_user_ids:
        return

    # 短信回复功能
    if (update.message.reply_to_message and not update.message.document and update.message.text):
        state = get_state(ctx)
        replied_id = update.message.reply_to_message.message_id
        phone = state.sms_reply_map.get(replied_id)
        if phone:
            await _handle_sms_reply(update, ctx, phone)
            return

    # 列配置输入
    if ctx.user_data.get("waiting_user_cols"):
        ctx.user_data["waiting_user_cols"] = False
        await _handle_cols_input(update, ctx)
        return

    # 批量文本粘贴
    if ctx.user_data.get("waiting_batch"):
        ctx.user_data["waiting_batch"] = False
        await _handle_batch_paste(update, ctx)
        return


async def _handle_sms_reply(update: Update, ctx, phone: str):
    """短信回复：回复 Telegram 通知 → 自动回短信"""
    import logging
    log = logging.getLogger(__name__)
    reply_body = update.message.text.strip()
    if not reply_body:
        await update.message.reply_text("内容不能为空")
        return
    from bot.utils.formatting import mask_phone
    tip = await update.message.reply_text(f"📤 正在回复 {mask_phone(phone)}...", parse_mode=None)
    log.info(f"短信回复 → {phone} | {reply_body[:40]}")

    state = get_state(ctx)
    had_running = state.task_running and not state.priority_held
    if had_running:
        state.acquire_priority()
        import asyncio
        await asyncio.sleep(2)
    try:
        sender = ctx.bot_data["sender"]
        ok, info = await sender.send(phone, reply_body)
        if ok:
            await tip.edit_text(f"✅ 已回复 {mask_phone(phone)}\n内容：{reply_body[:100]}", parse_mode=None)
        else:
            await tip.edit_text(f"❌ 回复失败：{info}", parse_mode=None)
    except Exception as e:
        await tip.edit_text(f"❌ 回复异常：{e}", parse_mode=None)
    finally:
        if had_running:
            state.release_priority()


async def _handle_cols_input(update: Update, ctx):
    """处理列配置文本输入"""
    raw = update.message.text.strip()
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    cols = [c.strip() for c in lines[0].replace("，", ",").split(",") if c.strip()]
    date_fmt = lines[1].strip() if len(lines) > 1 else None
    if not cols:
        await update.message.reply_text("❌ 第一行请填列名"); return
    ctx.user_data["pending_user_cols"] = cols
    if date_fmt:
        ctx.user_data["pending_date_fmt"] = date_fmt
    preview = f"列：{'、'.join(cols)}"
    if date_fmt:
        preview += f"\n日期格式：{date_fmt}"
    await update.message.reply_text(
        f"新配置预览：\n\n{preview}\n\n确认？",
        reply_markup=kb(
            [("✅ 确认", "cb_user_cols_confirm"), ("✏️ 重新输入", "cb_user_cols_edit")],
        ),
    )


async def _handle_batch_paste(update: Update, ctx):
    """处理粘贴的批量文本"""
    tasks, errors = parse_batch_text(update.message.text)
    if not tasks:
        await update.message.reply_text("❌ 没有有效数据")
        return

    cfg = get_cfg(ctx)
    eta = calc_eta(len(tasks), cfg.interval_min, cfg.interval_max)
    preview = "\n\n".join(f"📞 {t['phone']}\n💬 {t['message'][:60]}" for t in tasks[:3])
    if len(tasks) > 3:
        preview += f"\n\n_...共 {len(tasks)} 条_"
    err_text = f"\n⚠️ {len(errors)} 行解析失败" if errors else ""

    ctx.user_data["pending_tasks"] = tasks
    await update.message.reply_text(
        f"*解析完成，共 {len(tasks)} 条*{err_text}\n"
        f"⏱ {cfg.interval_min}–{cfg.interval_max}s　预计 {eta} 分钟\n\n"
        f"*预览：*\n\n{preview}\n\n确认发送？",
        parse_mode="Markdown",
        reply_markup=kb([("✅ 开始发送", "cb_import_confirm"), ("❌ 取消", "cb_import_cancel")]),
    )


async def _handle_batch_txt(update: Update, ctx):
    """处理上传的 .txt 批量文件"""
    state = get_state(ctx)
    if state.task_running:
        await update.message.reply_text("⚠️ 当前有任务运行中，请先 /stop")
        return

    tip = await update.message.reply_text("⏳ 正在解析...")
    try:
        file = await update.message.document.get_file()
        raw = bytes(await file.download_as_bytearray())
        text, err = parse_batch_file(raw)
        if not text:
            await tip.edit_text(f"❌ {err}")
            return

        tasks, errors = parse_batch_text(text)
        if not tasks:
            await tip.edit_text("❌ 没有有效数据" + (f"\n\n{chr(10).join(errors[:10])}" if errors else ""))
            return

        cfg = get_cfg(ctx)
        eta = calc_eta(len(tasks), cfg.interval_min, cfg.interval_max)
        preview = "\n\n".join(f"📞 {t['phone']}\n💬 {t['message'][:60]}" for t in tasks[:3])
        if len(tasks) > 3:
            preview += f"\n\n...共 {len(tasks)} 条"
        err_text = f"\n⚠️ {len(errors)} 行解析失败" if errors else ""

        ctx.user_data["pending_tasks"] = tasks
        await tip.edit_text(
            f"*📄 解析完成*\n\n"
            f"📋 共 {len(tasks)} 条{err_text}\n"
            f"⏱ 预计 {eta} 分钟\n\n"
            f"*预览：*\n\n{preview}\n\n确认发送？",
            parse_mode="Markdown",
            reply_markup=kb([("✅ 开始发送", "cb_import_confirm"), ("❌ 取消", "cb_import_cancel")]),
        )
    except Exception as e:
        await tip.edit_text(f"❌ 解析失败：{e}")

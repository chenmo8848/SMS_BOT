# -*- coding: utf-8 -*-
"""SMS Bot v6 — 短信模板管理"""

from telegram import Update
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from bot.handlers.common import auth, get_cfg, get_state
from bot.handlers.menu import back_to_menu
from bot.utils.keyboard import kb


def register(app):
    app.add_handler(CommandHandler("template", cmd_template))
    app.add_handler(CallbackQueryHandler(cb_template, pattern=r"^cb_template$"))
    app.add_handler(CallbackQueryHandler(cb_tpl_confirm, pattern=r"^cb_tpl_confirm$"))
    app.add_handler(CallbackQueryHandler(cb_tpl_edit, pattern=r"^cb_tpl_edit$"))


@auth
async def cmd_template(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    state = get_state(ctx)
    cfg = get_cfg(ctx)
    if ctx.args:
        new_tpl = " ".join(ctx.args)
        preview = (new_tpl
                   .replace("{姓名}", "张三")
                   .replace("{卡号}", "8473")
                   .replace("{日期}", f"2025{cfg.sms_date_sep}01{cfg.sms_date_sep}27")
                   .replace("{金额}", "4000"))
        ctx.user_data["pending_template"] = new_tpl
        await update.message.reply_text(
            f"*模板预览*\n\n{preview}\n\n确认使用此模板？",
            parse_mode="Markdown",
            reply_markup=kb([("✅ 确认", "cb_tpl_confirm"), ("✏️ 继续修改", "cb_tpl_edit")]),
        )
    else:
        await update.message.reply_text(
            "*📝 短信模板*\n━━━━━━━━━━━━━━━\n\n"
            f"*当前模板：*\n{state.sms_template}\n\n"
            "*占位符：*\n"
            "`{姓名}` 姓名　`{卡号}` 卡号后4位\n"
            "`{日期}` 放款日期　`{金额}` 金额\n\n"
            "修改：`/template 新内容`",
            parse_mode="Markdown",
            reply_markup=kb([("✏️ 修改模板", "cb_tpl_edit")]),
        )


async def cb_template(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    state = get_state(ctx)
    await q.edit_message_text(
        "*📝 短信模板*\n━━━━━━━━━━━━━━━\n\n"
        f"*当前模板：*\n{state.sms_template}\n\n"
        "*占位符：*\n"
        "`{姓名}` 姓名　`{卡号}` 卡号后4位\n"
        "`{日期}` 放款日期　`{金额}` 金额\n\n"
        "_修改：发送_ `/template 新内容`",
        parse_mode="Markdown",
        reply_markup=kb([("✏️ 修改模板", "cb_tpl_edit"), ("🔙 主菜单", "menu_main")]),
    )


async def cb_tpl_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    new_tpl = ctx.user_data.pop("pending_template", None)
    if not new_tpl:
        await q.edit_message_text("❌ 已过期，请重新发 /template 新内容")
        return
    get_state(ctx).sms_template = new_tpl
    await back_to_menu(q, ctx, f"✅ 模板已更新\n\n{new_tpl}")


async def cb_tpl_edit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data.pop("pending_template", None)
    await q.edit_message_text(
        "✏️ 发送新模板：\n\n"
        "`/template 新模板内容`\n\n"
        "示例：\n"
        "`/template {姓名}您好，尾号{卡号}的卡于{日期}申请的{金额}元已逾期`",
        parse_mode="Markdown",
    )

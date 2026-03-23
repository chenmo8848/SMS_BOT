# -*- coding: utf-8 -*-
"""SMS Bot v6 — Handler 统一注册"""

from telegram.ext import Application
from bot.handlers import menu, send, task, monitor, settings, template, data, log_view, landtest, license


def register_all(app: Application):
    """注册所有 handler 到 app"""
    for module in [menu, send, task, monitor, settings,
                   template, data, log_view, landtest, license]:
        module.register(app)

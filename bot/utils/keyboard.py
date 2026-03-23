# -*- coding: utf-8 -*-
"""SMS Bot v6 — 键盘构建工具"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def kb(*rows):
    """快速构建 InlineKeyboard
    每个 row 是 (text, callback_data) 元组的列表
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text, callback_data=data) for text, data in row]
        for row in rows
    ])


def kb_rows(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    """从二维列表构建键盘（动态行数）"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t, callback_data=d) for t, d in row]
        for row in rows
    ])

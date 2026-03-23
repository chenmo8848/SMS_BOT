# -*- coding: utf-8 -*-
"""SMS Bot v6 — 通知服务（个人+群组，Markdown 失败自动降级纯文本）"""

import logging
from typing import Optional
from telegram import Bot, Message
from bot.config import BotConfig

log = logging.getLogger(__name__)


class Notifier:
    """统一通知：同时推送给个人和群组（如有）"""

    def __init__(self, cfg: BotConfig):
        self._cfg = cfg

    async def send(self, bot: Bot, text: str,
                   parse_mode: str = "Markdown") -> Optional[Message]:
        """发送通知，返回个人通知的 Message 对象（用于短信回复追踪）"""
        user_msg = await self._safe_send(bot, self._cfg.notify_user_id, text, parse_mode)
        if self._cfg.notify_group_id:
            await self._safe_send(bot, self._cfg.notify_group_id, text, parse_mode)
        return user_msg

    async def send_to_user(self, bot: Bot, text: str,
                           parse_mode: str = "Markdown") -> Optional[Message]:
        """仅发送给用户（不推群组）"""
        return await self._safe_send(bot, self._cfg.notify_user_id, text, parse_mode)

    @staticmethod
    async def _safe_send(bot: Bot, chat_id: int, text: str,
                         parse_mode: str = "Markdown") -> Optional[Message]:
        """安全发送，Markdown 失败自动降级纯文本"""
        try:
            return await bot.send_message(
                chat_id=chat_id, text=text, parse_mode=parse_mode
            )
        except Exception as e:
            err = str(e).lower()
            if parse_mode and any(k in err for k in ("parse", "can't", "entities", "markdown")):
                try:
                    clean = text.replace("*", "").replace("_", "").replace("`", "")
                    return await bot.send_message(chat_id=chat_id, text=clean)
                except Exception as e2:
                    log.error(f"纯文本降级也失败 [{chat_id}]: {e2}")
                    return None
            log.error(f"消息发送失败 [{chat_id}]: {e}")
            return None

# -*- coding: utf-8 -*-
"""SMS Bot v6 — phone.db 数据库操作（路径解析、短信读取、发送确认、SIM 管理）"""

import os, glob, time, sqlite3, logging
from typing import Optional
from bot.models.sms import SmsMessage, SimCard
from bot.utils.formatting import normalize_phone

log = logging.getLogger(__name__)

# Phone Link 包名（支持多版本）
_PHONE_LINK_PACKAGES = [
    "Microsoft.YourPhone_8wekyb3d8bbwe",
    "Microsoft.Phone_8wekyb3d8bbwe",
]


class PhoneDB:
    """phone.db 的全部读写操作"""

    def __init__(self):
        self._db_path_cache: Optional[str] = None

    def resolve_path(self) -> Optional[str]:
        """解析 phone.db 实际路径，支持多版本 Phone Link，带缓存"""
        if self._db_path_cache and os.path.exists(self._db_path_cache):
            return self._db_path_cache
        local = os.path.expandvars(r"%LOCALAPPDATA%")
        for pkg in _PHONE_LINK_PACKAGES:
            pattern = os.path.join(
                local, "Packages", pkg,
                "LocalCache", "Indexed", "*",
                "System", "Database", "phone.db",
            )
            found = glob.glob(pattern)
            if found:
                self._db_path_cache = found[0]
                log.info(f"phone.db 路径: {self._db_path_cache}")
                return self._db_path_cache
        log.warning("找不到 phone.db（手机连接未配对或未同步）")
        return None

    def _connect_ro(self) -> Optional[sqlite3.Connection]:
        """只读模式连接"""
        db = self.resolve_path()
        if not db:
            return None
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=3)
            conn.row_factory = sqlite3.Row
            return conn
        except Exception as e:
            log.debug(f"DB 连接失败: {e}")
            return None

    # ─── 短信读取 ───

    def read_new_sms(self, since_id: int = 0) -> list[SmsMessage]:
        """读取 type=1（收到）的新短信"""
        conn = self._connect_ro()
        if not conn:
            return []
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT message_id, from_address, body, timestamp
                FROM message
                WHERE message_id > ? AND type = 1 AND body != ''
                ORDER BY message_id ASC
            """, (since_id,))
            msgs = [
                SmsMessage(
                    message_id=row["message_id"],
                    from_address=(row["from_address"] or "").strip(),
                    body=(row["body"] or "").strip(),
                    timestamp=row["timestamp"],
                )
                for row in cur.fetchall()
            ]
            conn.close()
            return msgs
        except Exception as e:
            log.debug(f"read_new_sms: {e}")
            return []

    def get_max_message_id(self, msg_type: int = 1) -> int:
        """获取指定类型的最大 message_id（1=收到，2=发出）"""
        conn = self._connect_ro()
        if not conn:
            return 0
        try:
            cur = conn.cursor()
            cur.execute("SELECT MAX(message_id) FROM message WHERE type=?", (msg_type,))
            result = cur.fetchone()[0]
            conn.close()
            return result or 0
        except Exception as e:
            log.debug(f"get_max_message_id: {e}")
            return 0

    def get_max_sent_id(self) -> int:
        """获取最大已发送 message_id"""
        return self.get_max_message_id(msg_type=2)

    def confirm_sent(self, before_id: int, phone: str = "", timeout: int = 15) -> bool:
        """发送后轮询确认是否真正发出，最多等 timeout 秒"""
        db = self.resolve_path()
        if not db:
            return False
        phone_norm = normalize_phone(phone)
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2)
            cur = conn.cursor()
            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    cur.execute(
                        "SELECT to_address FROM message WHERE type=2 AND message_id > ?",
                        (before_id,),
                    )
                    for row in cur.fetchall():
                        to_addr = normalize_phone(row[0] or "")
                        if (not phone_norm or to_addr == phone_norm
                                or phone_norm in to_addr or to_addr in phone_norm):
                            conn.close()
                            return True
                except Exception:
                    pass
                time.sleep(2)
            conn.close()
        except Exception:
            pass
        return False

    def get_last_sent_body(self) -> str:
        """读取最后一条发出短信的内容"""
        conn = self._connect_ro()
        if not conn:
            return ""
        try:
            row = conn.execute(
                "SELECT body FROM message WHERE type=2 ORDER BY message_id DESC LIMIT 1"
            ).fetchone()
            conn.close()
            return row[0] if row and row[0] else ""
        except Exception:
            return ""

    def get_db_age_seconds(self) -> Optional[float]:
        """获取 phone.db 最后修改距今的秒数"""
        db = self.resolve_path()
        if not db or not os.path.exists(db):
            return None
        try:
            return time.time() - os.path.getmtime(db)
        except Exception:
            return None

    # ─── SIM 卡管理 ───

    def get_sim_cards(self) -> list[SimCard]:
        """读取所有 SIM 卡"""
        conn = self._connect_ro()
        if not conn:
            return []
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT subscription_id, sim_slot_index, name, number,
                       is_default_sms_subscription
                FROM subscription ORDER BY sim_slot_index
            """)
            cards = [
                SimCard(
                    subscription_id=r["subscription_id"],
                    sim_slot_index=r["sim_slot_index"],
                    name=r["name"] or "",
                    number=r["number"] or "",
                    is_default=bool(r["is_default_sms_subscription"]),
                )
                for r in cur.fetchall()
            ]
            conn.close()
            return cards
        except Exception as e:
            log.debug(f"get_sim_cards: {e}")
            return []

    def set_default_sim(self, subscription_id: int) -> bool:
        """切换默认发送 SIM 卡（唯一的写操作，用 WAL + 短事务）"""
        db = self.resolve_path()
        if not db:
            return False
        try:
            conn = sqlite3.connect(db, timeout=5, isolation_level="DEFERRED")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=3000")
            cur = conn.cursor()
            cur.execute("UPDATE subscription SET is_default_sms_subscription = 0")
            cur.execute("UPDATE subscription SET is_default_subscription = 0")
            cur.execute("""
                UPDATE subscription
                SET is_default_sms_subscription = 1, is_default_subscription = 1
                WHERE subscription_id = ?
            """, (subscription_id,))
            conn.commit()
            conn.close()
            log.info(f"SIM 切换成功: subscription_id={subscription_id}")
            return True
        except Exception as e:
            log.warning(f"set_default_sim: {e}")
            return False

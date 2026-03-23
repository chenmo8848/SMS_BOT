# -*- coding: utf-8 -*-
"""SMS Bot v6 — 授权验证服务（机器码 + Cloudflare Workers 联网验证）"""

import os, hashlib, json, logging, time
from typing import Optional
from datetime import datetime

log = logging.getLogger(__name__)

# 授权缓存文件（验证通过后缓存，避免每次发送都联网）
_LICENSE_CACHE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "license.dat"
)

# 验证服务器地址（Cloudflare Workers，不暴露真实 IP）
# 安装时由 setup.py 写入 config.json
LICENSE_API_URL = ""


class LicenseError(Exception):
    """授权相关异常"""
    pass


def get_machine_id() -> str:
    """
    生成机器码：读取 CPU ID + 硬盘序列号 + Windows 产品 ID
    用 SHA256 哈希后取前 16 位，格式化为 XXXX-XXXX-XXXX-XXXX
    """
    parts = []

    # CPU ID
    try:
        import subprocess
        r = subprocess.run(
            ["wmic", "cpu", "get", "ProcessorId", "/value"],
            capture_output=True, text=True, timeout=10, errors="replace"
        )
        for line in r.stdout.splitlines():
            if "ProcessorId=" in line:
                parts.append(line.split("=", 1)[1].strip())
                break
    except Exception:
        parts.append("CPU_UNKNOWN")

    # 硬盘序列号
    try:
        r = subprocess.run(
            ["wmic", "diskdrive", "get", "SerialNumber", "/value"],
            capture_output=True, text=True, timeout=10, errors="replace"
        )
        for line in r.stdout.splitlines():
            if "SerialNumber=" in line:
                sn = line.split("=", 1)[1].strip()
                if sn:
                    parts.append(sn)
                    break
    except Exception:
        parts.append("DISK_UNKNOWN")

    # Windows 产品 ID
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
        )
        product_id, _ = winreg.QueryValueEx(key, "ProductId")
        winreg.CloseKey(key)
        parts.append(product_id)
    except Exception:
        parts.append("WIN_UNKNOWN")

    # 拼接 + SHA256
    raw = "|".join(parts)
    h = hashlib.sha256(raw.encode()).hexdigest()[:16].upper()
    return f"{h[:4]}-{h[4:8]}-{h[8:12]}-{h[12:16]}"


def verify_online(machine_id: str, api_url: str) -> dict:
    """
    联网验证授权
    返回: {"valid": True/False, "expires": "2026-06-20", "msg": "..."}
    """
    import httpx

    try:
        r = httpx.get(
            f"{api_url}/verify",
            params={"machine_id": machine_id},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            return data
        else:
            return {"valid": False, "msg": f"服务器返回 {r.status_code}"}
    except httpx.TimeoutException:
        return {"valid": False, "msg": "验证服务器连接超时"}
    except Exception as e:
        return {"valid": False, "msg": f"验证失败: {e}"}


def save_cache(machine_id: str, result: dict):
    """缓存验证结果（用于减少联网频率）"""
    try:
        cache = {
            "machine_id": machine_id,
            "valid": result.get("valid", False),
            "expires": result.get("expires", ""),
            "cached_at": datetime.now().isoformat(),
            "check_hash": _make_check_hash(machine_id, result),
        }
        with open(_LICENSE_CACHE, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except Exception as e:
        log.debug(f"缓存写入失败: {e}")


def load_cache(machine_id: str) -> Optional[dict]:
    """读取缓存的验证结果"""
    if not os.path.exists(_LICENSE_CACHE):
        return None
    try:
        with open(_LICENSE_CACHE, encoding="utf-8") as f:
            cache = json.load(f)
        # 校验缓存完整性
        if cache.get("machine_id") != machine_id:
            return None
        expected_hash = _make_check_hash(machine_id, cache)
        if cache.get("check_hash") != expected_hash:
            return None  # 被篡改
        return cache
    except Exception:
        return None


def _make_check_hash(machine_id: str, data: dict) -> str:
    """生成缓存校验哈希（防篡改）"""
    raw = f"{machine_id}|{data.get('valid','')}|{data.get('expires','')}|SMS_BOT_V6_SALT"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def is_expired(expires_str: str) -> bool:
    """检查是否过期"""
    if not expires_str or expires_str == "permanent":
        return False
    try:
        exp = datetime.strptime(expires_str, "%Y-%m-%d")
        return datetime.now() > exp
    except Exception:
        return False


class LicenseManager:
    """授权管理器 — 启动验证 + 运行时轻量检查"""

    def __init__(self, api_url: str):
        self._api_url = api_url
        self._machine_id = None
        self._valid = False
        self._expires = ""
        self._last_check = 0
        self.last_verify_result: Optional[dict] = None
        self._admin_contact: str = ""

    @property
    def machine_id(self) -> str:
        if not self._machine_id:
            self._machine_id = get_machine_id()
        return self._machine_id

    @property
    def is_valid(self) -> bool:
        return self._valid

    @property
    def expires(self) -> str:
        return self._expires

    @property
    def admin_contact(self) -> str:
        """管理员 Telegram 用户名（从服务端获取，你改一次所有客户自动生效）"""
        return self._admin_contact

    @property
    def admin_link(self) -> str:
        """可点击的管理员链接（Markdown 格式）"""
        name = self._admin_contact.strip().lstrip("@")
        if name:
            return f"[@{name}](https://t.me/{name})"
        return "管理员"

    @property
    def admin_mention(self) -> str:
        """纯文本 @用户名"""
        name = self._admin_contact.strip().lstrip("@")
        return f"@{name}" if name else "管理员"

    def full_verify(self) -> tuple[bool, str]:
        """
        完整验证（启动时调用）
        1. 联网验证
        2. 联网失败时检查本地缓存（缓存最多有效 24 小时）
        返回: (通过, 消息)
        """
        mid = self.machine_id
        log.info(f"机器码: {mid}")

        if not self._api_url:
            return False, "授权服务器地址未配置"

        # 联网验证
        result = verify_online(mid, self._api_url)

        # 不管验证通过与否，都更新管理员联系方式
        if result.get("admin_contact"):
            self._admin_contact = result["admin_contact"]

        if result.get("valid"):
            self._valid = True
            self._expires = result.get("expires", "")
            self._last_check = time.time()
            self.last_verify_result = result
            save_cache(mid, result)

            if self._expires and self._expires != "permanent":
                return True, f"授权有效，到期日：{self._expires}"
            return True, "授权有效（永久）"

        # 联网失败 → 检查缓存
        if "超时" in result.get("msg", "") or "连接" in result.get("msg", ""):
            cache = load_cache(mid)
            if cache and cache.get("valid"):
                # 缓存不超过 24 小时
                try:
                    cached_time = datetime.fromisoformat(cache["cached_at"])
                    age_hours = (datetime.now() - cached_time).total_seconds() / 3600
                    if age_hours <= 24 and not is_expired(cache.get("expires", "")):
                        self._valid = True
                        self._expires = cache.get("expires", "")
                        self._last_check = time.time()
                        log.info(f"离线缓存验证通过（缓存 {age_hours:.1f} 小时前）")
                        return True, f"离线验证通过（缓存有效）\n下次联网时将重新验证"
                except Exception:
                    pass

        self._valid = False
        return False, result.get("msg", "授权验证失败")

    def light_check(self) -> bool:
        """
        轻量检查（发送短信时调用）
        不联网，只检查内存状态 + 过期时间
        每 6 小时强制重新联网验证一次
        """
        if not self._valid:
            return False

        # 检查过期
        if self._expires and self._expires != "permanent":
            if is_expired(self._expires):
                self._valid = False
                log.warning("授权已过期")
                return False

        # 每 6 小时重新联网验证
        if time.time() - self._last_check > 6 * 3600:
            log.info("距上次验证超过 6 小时，重新验证")
            result = verify_online(self.machine_id, self._api_url)
            if result.get("valid"):
                self._valid = True
                self._expires = result.get("expires", "")
                self._last_check = time.time()
                save_cache(self.machine_id, result)
            else:
                # 联网失败不立即吊销（可能只是网络波动）
                # 但记录日志
                log.warning(f"定期重新验证失败: {result.get('msg')}")
                # 如果连续两个周期（12小时）都验证失败，才吊销
                if time.time() - self._last_check > 12 * 3600:
                    self._valid = False
                    log.warning("连续 12 小时验证失败，授权已暂停")
                    return False

        return True

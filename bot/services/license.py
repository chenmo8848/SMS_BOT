# -*- coding: utf-8 -*-
"""SMS Bot v6 — 授权验证服务（对接 Auth Server API）"""

import os, hashlib, json, logging, time, platform, threading, base64
from typing import Optional
from datetime import datetime

log = logging.getLogger(__name__)

# 授权缓存文件
_LICENSE_CACHE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "license.dat"
)

# 内置服务端地址（混淆存储）
_E = b'YUhSMGNITTZMeTlzYVdObGJuTmxMamt4T0RnNE15NWpiMjA9'
def _r():
    try:
        return base64.b64decode(base64.b64decode(_E)).decode()
    except Exception:
        return ""


class LicenseError(Exception):
    """授权相关异常"""
    pass


def get_machine_id() -> str:
    """
    生成机器码：读取 CPU ID + 硬盘序列号 + Windows 产品 ID
    用 SHA256 哈希，格式化为 XXXX-XXXX-XXXX-XXXX
    同时作为 device_id 发给服务端
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
        import subprocess
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


def _get_device_info() -> str:
    """获取设备描述信息"""
    try:
        return f"{platform.node()} | {platform.system()} {platform.release()} | {platform.machine()}"
    except Exception:
        return "Unknown"


def verify_online(device_id: str, api_url: str) -> dict:
    """
    联网验证授权（POST /api/client/verify）
    返回: {"valid": True/False, "expires": "...", "msg": "...", "trial": bool, ...}
    """
    import httpx

    try:
        r = httpx.post(
            f"{api_url.rstrip('/')}/api/client/verify",
            json={
                "device_id": device_id,
                "device_info": _get_device_info(),
                "client_version": "6.0"
            },
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            # 转换服务端响应格式，兼容客户端现有逻辑
            status = data.get("status")
            remaining = data.get("remaining_seconds", 0)
            is_trial = data.get("is_trial", False)
            expires_at = data.get("expires_at", "")

            if status == "ok":
                # 计算天数
                days_left = remaining // 86400
                hours_left = remaining // 3600
                # 转换 expires 为日期格式
                expires_date = ""
                if expires_at:
                    try:
                        dt = datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S")
                        expires_date = dt.strftime("%Y-%m-%d")
                    except Exception:
                        expires_date = expires_at[:10] if len(expires_at) >= 10 else expires_at

                return {
                    "valid": True,
                    "expires": expires_date,
                    "days_left": days_left,
                    "trial": is_trial,
                    "trial_hours_left": hours_left if is_trial else 0,
                    "remaining_seconds": remaining,
                    "heartbeat_interval": data.get("heartbeat_interval", 300),
                    "msg": data.get("message", "授权有效"),
                    "admin_contact": "",
                }
            elif status == "banned":
                return {"valid": False, "msg": "设备已被封禁", "admin_contact": ""}
            elif status == "expired":
                return {
                    "valid": False,
                    "msg": "授权已过期",
                    "trial": is_trial,
                    "admin_contact": "",
                }
            else:
                return {"valid": False, "msg": data.get("message", "验证失败"), "admin_contact": ""}
        else:
            return {"valid": False, "msg": f"服务器返回 {r.status_code}"}
    except httpx.TimeoutException:
        return {"valid": False, "msg": "验证服务器连接超时"}
    except Exception as e:
        return {"valid": False, "msg": f"验证失败: {e}"}


def send_heartbeat(device_id: str, api_url: str) -> dict:
    """发送心跳"""
    import httpx
    try:
        r = httpx.post(
            f"{api_url.rstrip('/')}/api/client/heartbeat",
            json={"device_id": device_id, "client_version": "6.0"},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()
        return {"status": "error"}
    except Exception as e:
        log.debug(f"心跳发送失败: {e}")
        return {"status": "error"}


def activate_key(device_id: str, api_url: str, license_key: str) -> dict:
    """激活卡密"""
    import httpx
    try:
        r = httpx.post(
            f"{api_url.rstrip('/')}/api/client/activate",
            json={"device_id": device_id, "license_key": license_key},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("status") == "ok":
                remaining = data.get("remaining_seconds", 0)
                expires_at = data.get("expires_at", "")
                expires_date = ""
                if expires_at:
                    try:
                        dt = datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S")
                        expires_date = dt.strftime("%Y-%m-%d")
                    except Exception:
                        expires_date = expires_at[:10]
                return {
                    "valid": True,
                    "expires": expires_date,
                    "days_left": remaining // 86400,
                    "remaining_seconds": remaining,
                    "msg": data.get("message", "激活成功"),
                }
            else:
                return {"valid": False, "msg": data.get("message", "激活失败")}
        return {"valid": False, "msg": f"服务器返回 {r.status_code}"}
    except Exception as e:
        return {"valid": False, "msg": f"激活失败: {e}"}


def save_cache(machine_id: str, result: dict):
    """缓存验证结果"""
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
    """读取缓存"""
    if not os.path.exists(_LICENSE_CACHE):
        return None
    try:
        with open(_LICENSE_CACHE, encoding="utf-8") as f:
            cache = json.load(f)
        if cache.get("machine_id") != machine_id:
            return None
        expected_hash = _make_check_hash(machine_id, cache)
        if cache.get("check_hash") != expected_hash:
            return None
        return cache
    except Exception:
        return None


def _make_check_hash(machine_id: str, data: dict) -> str:
    """缓存校验哈希"""
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
    """授权管理器 — 启动验证 + 心跳 + 卡密激活 + 运行时检查"""

    def __init__(self, api_url: str = ""):
        self._api_url = api_url or _r()
        self._machine_id = None
        self._valid = False
        self._expires = ""
        self._last_check = 0
        self.last_verify_result: Optional[dict] = None
        self._admin_contact: str = ""
        self._heartbeat_interval = 300
        self._heartbeat_thread = None
        self._stop_heartbeat = threading.Event()

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
        return self._admin_contact

    @property
    def admin_link(self) -> str:
        name = self._admin_contact.strip().lstrip("@")
        if name:
            return f"[@{name}](https://t.me/{name})"
        return "管理员"

    @property
    def admin_mention(self) -> str:
        name = self._admin_contact.strip().lstrip("@")
        return f"@{name}" if name else "管理员"

    def full_verify(self) -> tuple[bool, str]:
        """
        完整验证（启动时调用）
        1. 联网验证
        2. 失败时检查缓存
        返回: (通过, 消息)
        """
        mid = self.machine_id
        log.info(f"机器码: {mid}")

        if not self._api_url:
            return False, "授权服务器地址未配置"

        # 联网验证
        result = verify_online(mid, self._api_url)

        if result.get("admin_contact"):
            self._admin_contact = result["admin_contact"]

        if result.get("valid"):
            self._valid = True
            self._expires = result.get("expires", "")
            self._last_check = time.time()
            self.last_verify_result = result
            self._heartbeat_interval = result.get("heartbeat_interval", 300)
            save_cache(mid, result)

            # 启动心跳线程
            self._start_heartbeat()

            if result.get("trial"):
                hours = result.get("trial_hours_left", 24)
                return True, f"试用中，剩余 {hours} 小时"
            if self._expires:
                days = result.get("days_left", 0)
                return True, f"授权有效，到期日：{self._expires}（剩 {days} 天）"
            return True, "授权有效"

        # 联网失败 → 检查缓存
        if "超时" in result.get("msg", "") or "连接" in result.get("msg", "") or "失败" in result.get("msg", ""):
            cache = load_cache(mid)
            if cache and cache.get("valid"):
                try:
                    cached_time = datetime.fromisoformat(cache["cached_at"])
                    age_hours = (datetime.now() - cached_time).total_seconds() / 3600
                    if age_hours <= 24 and not is_expired(cache.get("expires", "")):
                        self._valid = True
                        self._expires = cache.get("expires", "")
                        self._last_check = time.time()
                        log.info(f"离线缓存验证通过（缓存 {age_hours:.1f} 小时前）")
                        self._start_heartbeat()
                        return True, f"离线验证通过（缓存有效）\n下次联网时将重新验证"
                except Exception:
                    pass

        self._valid = False
        return False, result.get("msg", "授权验证失败")

    def activate(self, license_key: str) -> tuple[bool, str]:
        """激活卡密"""
        mid = self.machine_id
        if not self._api_url:
            return False, "授权服务器地址未配置"

        result = activate_key(mid, self._api_url, license_key)
        if result.get("valid"):
            self._valid = True
            self._expires = result.get("expires", "")
            self._last_check = time.time()
            self.last_verify_result = result
            save_cache(mid, result)
            self._start_heartbeat()
            return True, result.get("msg", "激活成功")
        return False, result.get("msg", "激活失败")

    def light_check(self) -> bool:
        """
        轻量检查（发送短信时调用）
        不联网，只检查内存状态 + 过期时间
        每 6 小时强制重新联网验证
        """
        if not self._valid:
            return False

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
                log.warning(f"定期重新验证失败: {result.get('msg')}")
                if time.time() - self._last_check > 12 * 3600:
                    self._valid = False
                    log.warning("连续 12 小时验证失败，授权已暂停")
                    return False

        return True

    def _start_heartbeat(self):
        """启动后台心跳线程"""
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return

        self._stop_heartbeat.clear()

        def _loop():
            while not self._stop_heartbeat.is_set():
                self._stop_heartbeat.wait(self._heartbeat_interval)
                if self._stop_heartbeat.is_set():
                    break
                result = send_heartbeat(self.machine_id, self._api_url)
                if result.get("status") == "ok":
                    remaining = result.get("remaining_seconds", 0)
                    if remaining > 0:
                        self._heartbeat_interval = result.get("heartbeat_interval", 300)
                    log.debug(f"心跳成功，剩余 {remaining}s")
                elif result.get("status") in ("expired", "banned"):
                    self._valid = False
                    log.warning(f"心跳返回: {result.get('status')}")
                    break

        self._heartbeat_thread = threading.Thread(target=_loop, daemon=True, name="heartbeat")
        self._heartbeat_thread.start()
        log.info(f"心跳线程已启动，间隔 {self._heartbeat_interval}s")

    def stop_heartbeat(self):
        """停止心跳"""
        self._stop_heartbeat.set()

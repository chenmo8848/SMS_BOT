# -*- coding: utf-8 -*-
"""SMS Bot v6 — 授权验证服务（对接 Auth Server API）"""

import os, hashlib, json, logging, time, platform, threading, base64
from typing import Optional
from datetime import datetime, timezone, timedelta

log = logging.getLogger(__name__)

# 统一时区：Asia/Shanghai (UTC+8)
CST = timezone(timedelta(hours=8))

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


DEFAULT_API_URL = _r().rstrip("/")
DEFAULT_HEARTBEAT_INTERVAL = 300
DEFAULT_HEARTBEAT_TIMEOUT = 600
DEFAULT_MAX_OFFLINE_SECONDS = 3600


class LicenseError(Exception):
    """授权相关异常"""
    pass


def _now() -> datetime:
    """统一使用上海时间，与服务端一致"""
    return datetime.now(CST)


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


def _extract_admin(data: dict) -> str:
    """从服务端响应中提取管理员联系方式"""
    return data.get("admin_telegram", "") or data.get("admin_contact", "")


def _coerce_positive_int(value, default: int) -> int:
    try:
        parsed = int(value)
        return parsed if parsed > 0 else default
    except (TypeError, ValueError):
        return default


def _coerce_non_negative_int(value, default: int = 0) -> int:
    try:
        parsed = int(value)
        return parsed if parsed >= 0 else default
    except (TypeError, ValueError):
        return default


def _extract_policy(data: Optional[dict]) -> dict:
    payload = data or {}
    heartbeat_interval = _coerce_positive_int(
        payload.get("heartbeat_interval"), DEFAULT_HEARTBEAT_INTERVAL
    )
    heartbeat_timeout = _coerce_positive_int(
        payload.get("heartbeat_timeout"), DEFAULT_HEARTBEAT_TIMEOUT
    )
    heartbeat_timeout = max(heartbeat_timeout, heartbeat_interval)
    max_offline_seconds = _coerce_positive_int(
        payload.get("max_offline_seconds"), DEFAULT_MAX_OFFLINE_SECONDS
    )
    max_offline_seconds = max(max_offline_seconds, heartbeat_timeout)
    return {
        "heartbeat_interval": heartbeat_interval,
        "heartbeat_timeout": heartbeat_timeout,
        "max_offline_seconds": max_offline_seconds,
    }


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
        if r.status_code != 200:
            return {
                "valid": False,
                "msg": f"服务器返回 {r.status_code}",
                "temporary_error": True,
                **_extract_policy(None),
            }

        data = r.json()
        status = data.get("status")
        remaining = _coerce_non_negative_int(data.get("remaining_seconds"), 0)
        is_trial = bool(data.get("is_trial", False))
        expires_at = data.get("expires_at", "")
        admin = _extract_admin(data)
        base = {
            "temporary_error": False,
            "announcement": data.get("announcement", ""),
            "admin_contact": admin,
            **_extract_policy(data),
        }

        if status == "ok":
            days_left = remaining // 86400
            hours_left = remaining // 3600
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
                "msg": data.get("message", "授权有效"),
                **base,
            }
        if status == "banned":
            return {"valid": False, "msg": "设备已被封禁", **base}
        if status == "disabled":
            return {"valid": False, "msg": "授权已被禁用", **base}
        if status == "expired":
            return {
                "valid": False,
                "msg": "授权已过期",
                "trial": is_trial,
                "remaining_seconds": remaining,
                **base,
            }
        return {
            "valid": False,
            "msg": data.get("message", "验证失败"),
            **base,
        }
    except httpx.TimeoutException:
        return {
            "valid": False,
            "msg": "验证服务器连接超时",
            "temporary_error": True,
            **_extract_policy(None),
        }
    except Exception as e:
        return {
            "valid": False,
            "msg": f"验证失败: {e}",
            "temporary_error": True,
            **_extract_policy(None),
        }


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
            data = r.json()
            return {
                "status": data.get("status", "error"),
                "message": data.get("message", ""),
                "remaining_seconds": _coerce_non_negative_int(data.get("remaining_seconds"), 0),
                "temporary_error": False,
                "admin_contact": _extract_admin(data),
                "announcement": data.get("announcement", ""),
                **_extract_policy(data),
            }
        return {
            "status": "error",
            "message": f"服务器返回 {r.status_code}",
            "temporary_error": True,
            **_extract_policy(None),
        }
    except Exception as e:
        log.debug(f"心跳发送失败: {e}")
        return {
            "status": "error",
            "message": f"心跳发送失败: {e}",
            "temporary_error": True,
            **_extract_policy(None),
        }


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
            base = {
                "temporary_error": False,
                "announcement": data.get("announcement", ""),
                "admin_contact": _extract_admin(data),
                **_extract_policy(data),
            }
            if data.get("status") == "ok":
                remaining = _coerce_non_negative_int(data.get("remaining_seconds"), 0)
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
                    **base,
                }
            else:
                return {"valid": False, "msg": data.get("message", "激活失败"), **base}
        return {
            "valid": False,
            "msg": f"服务器返回 {r.status_code}",
            "temporary_error": True,
            **_extract_policy(None),
        }
    except Exception as e:
        return {
            "valid": False,
            "msg": f"激活失败: {e}",
            "temporary_error": True,
            **_extract_policy(None),
        }


def save_cache(machine_id: str, result: dict):
    """缓存验证结果"""
    try:
        cached_at = _now().isoformat()
        cache = {
            "machine_id": machine_id,
            "valid": result.get("valid", False),
            "expires": result.get("expires", ""),
            "trial": bool(result.get("trial", False)),
            "trial_hours_left": _coerce_non_negative_int(result.get("trial_hours_left"), 0),
            "days_left": _coerce_non_negative_int(result.get("days_left"), 0),
            "remaining_seconds": _coerce_non_negative_int(result.get("remaining_seconds"), 0),
            "heartbeat_interval": _coerce_positive_int(
                result.get("heartbeat_interval"), DEFAULT_HEARTBEAT_INTERVAL
            ),
            "heartbeat_timeout": _coerce_positive_int(
                result.get("heartbeat_timeout"), DEFAULT_HEARTBEAT_TIMEOUT
            ),
            "max_offline_seconds": _coerce_positive_int(
                result.get("max_offline_seconds"), DEFAULT_MAX_OFFLINE_SECONDS
            ),
            "announcement": result.get("announcement", ""),
            "admin_contact": result.get("admin_contact", ""),
            "cached_at": cached_at,
            "check_hash": _make_check_hash(machine_id, result, cached_at),
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
        expected_hash = _make_check_hash(machine_id, cache, cache.get("cached_at", ""))
        if cache.get("check_hash") != expected_hash:
            return None
        return cache
    except Exception:
        return None


def _make_check_hash(machine_id: str, data: dict, cached_at: str = "") -> str:
    """缓存校验哈希（含 cached_at 防篡改）"""
    raw = f"{machine_id}|{data.get('valid','')}|{data.get('expires','')}|{cached_at}|SMS_BOT_V6_SALT"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def is_expired(expires_str: str) -> bool:
    """检查是否过期（使用 UTC 时间比较）"""
    if not expires_str or expires_str == "permanent":
        return False
    try:
        exp = datetime.strptime(expires_str, "%Y-%m-%d").replace(tzinfo=CST)
        return _now() > exp
    except Exception:
        return False


class LicenseManager:
    """授权管理器 — 启动验证 + 心跳 + 卡密激活 + 运行时检查"""

    def __init__(self, api_url: str = ""):
        self._api_url = (api_url or DEFAULT_API_URL).rstrip("/")
        self._machine_id = None
        self._valid = False
        self._expires = ""
        self._last_check = time.time()  # 初始化为当前时间，避免首次 light_check 立即重验证
        self.last_verify_result: Optional[dict] = None
        self._admin_contact: str = ""
        self._announcement: str = ""
        self._heartbeat_interval = DEFAULT_HEARTBEAT_INTERVAL
        self._heartbeat_timeout = DEFAULT_HEARTBEAT_TIMEOUT
        self._max_offline_seconds = DEFAULT_MAX_OFFLINE_SECONDS
        self._last_server_contact_at = 0.0
        self._last_verify_attempt_at = 0.0
        self._heartbeat_thread = None
        self._stop_heartbeat = threading.Event()
        self._lock = threading.Lock()

    @property
    def machine_id(self) -> str:
        if not self._machine_id:
            self._machine_id = get_machine_id()
        return self._machine_id

    @property
    def is_valid(self) -> bool:
        with self._lock:
            return self._valid

    @property
    def expires(self) -> str:
        with self._lock:
            return self._expires

    @property
    def admin_contact(self) -> str:
        return self._admin_contact

    @property
    def announcement(self) -> str:
        return self._announcement

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

    def _apply_runtime_policy(self, data: Optional[dict]):
        if not data:
            return
        if data.get("admin_contact"):
            self._admin_contact = data["admin_contact"]
        if data.get("announcement"):
            self._announcement = data["announcement"]

        policy = _extract_policy(data)
        self._heartbeat_interval = policy["heartbeat_interval"]
        self._heartbeat_timeout = policy["heartbeat_timeout"]
        self._max_offline_seconds = policy["max_offline_seconds"]

    def _mark_server_contact(self, at: Optional[float] = None):
        with self._lock:
            self._last_server_contact_at = at if at is not None else time.time()

    def _within_offline_grace(self) -> bool:
        with self._lock:
            if not self._valid or self._last_server_contact_at <= 0:
                return False
            return (time.time() - self._last_server_contact_at) <= self._max_offline_seconds

    def _accept_valid_result(self, result: dict, *, contact_at: Optional[float] = None, save_result: bool = True):
        with self._lock:
            self._valid = True
            self._expires = result.get("expires", "")
            self._last_check = time.time()
        self.last_verify_result = result
        if save_result:
            save_cache(self.machine_id, result)
        self._mark_server_contact(contact_at)

    def refresh_status(self, *, respect_offline_grace: bool = True) -> tuple[bool, dict]:
        result = verify_online(self.machine_id, self._api_url)
        self._apply_runtime_policy(result)

        if result.get("valid"):
            self._accept_valid_result(result)
            return True, result

        if respect_offline_grace and result.get("temporary_error") and self._within_offline_grace():
            return True, result

        with self._lock:
            self._valid = False
        self.last_verify_result = {
            **(self.last_verify_result or {}),
            "valid": False,
            "msg": result.get("msg", "授权验证失败"),
            "temporary_error": bool(result.get("temporary_error")),
        }
        return False, result

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
            return False, "内置授权服务地址无效"

        # 联网验证
        result = verify_online(mid, self._api_url)
        self._apply_runtime_policy(result)

        if result.get("valid"):
            self._accept_valid_result(result)

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
        if result.get("temporary_error"):
            cache = load_cache(mid)
            if cache and cache.get("valid"):
                try:
                    cached_time = datetime.fromisoformat(cache["cached_at"])
                    if cached_time.tzinfo is None:
                        cached_time = cached_time.replace(tzinfo=CST)
                    age_seconds = (_now() - cached_time).total_seconds()
                    offline_limit = _coerce_positive_int(
                        cache.get("max_offline_seconds"), self._max_offline_seconds
                    )
                    if age_seconds <= offline_limit and not is_expired(cache.get("expires", "")):
                        self._apply_runtime_policy(cache)
                        remaining = max(
                            0,
                            _coerce_non_negative_int(cache.get("remaining_seconds"), 0) - int(age_seconds)
                        )
                        offline_result = {
                            **cache,
                            "valid": True,
                            "remaining_seconds": remaining,
                            "days_left": remaining // 86400,
                            "trial_hours_left": remaining // 3600 if cache.get("trial") else 0,
                            "msg": "离线缓存验证",
                        }
                        self._accept_valid_result(
                            offline_result,
                            contact_at=cached_time.timestamp(),
                            save_result=False,
                        )
                        log.info(f"离线缓存验证通过（缓存 {age_seconds / 3600:.1f} 小时前）")
                        self._start_heartbeat()
                        return True, f"离线验证通过（缓存有效）\n下次联网时将重新验证"
                except Exception:
                    pass

        with self._lock:
            self._valid = False
        self.last_verify_result = {
            **(self.last_verify_result or {}),
            "valid": False,
            "msg": result.get("msg", "授权验证失败"),
            "temporary_error": bool(result.get("temporary_error")),
        }
        return False, result.get("msg", "授权验证失败")

    def activate(self, license_key: str) -> tuple[bool, str]:
        """激活卡密"""
        mid = self.machine_id
        if not self._api_url:
            return False, "内置授权服务地址无效"

        result = activate_key(mid, self._api_url, license_key)
        self._apply_runtime_policy(result)
        if result.get("valid"):
            self._accept_valid_result(result)
            self._start_heartbeat()
            return True, result.get("msg", "激活成功")
        return False, result.get("msg", "激活失败")

    def light_check(self) -> bool:
        """
        轻量检查（发送短信时调用）
        不联网，只检查内存状态 + 过期时间
        每 6 小时强制重新联网验证
        """
        with self._lock:
            if not self._valid:
                return False
            expires = self._expires
            last_server_contact_at = self._last_server_contact_at
            last_verify_attempt_at = self._last_verify_attempt_at
            heartbeat_timeout = self._heartbeat_timeout
            heartbeat_interval = self._heartbeat_interval

        if expires and expires != "permanent":
            if is_expired(expires):
                with self._lock:
                    self._valid = False
                log.warning("授权已过期")
                return False

        now_ts = time.time()
        if last_server_contact_at > 0 and (now_ts - last_server_contact_at) <= heartbeat_timeout:
            return True

        retry_cooldown = max(30, min(heartbeat_interval, heartbeat_timeout))
        if last_verify_attempt_at > 0 and (now_ts - last_verify_attempt_at) < retry_cooldown:
            return self._within_offline_grace()

        with self._lock:
            self._last_verify_attempt_at = now_ts

        log.info("距上次服务端确认超过心跳超时，尝试重新验证")
        ok, result = self.refresh_status(respect_offline_grace=True)
        if ok:
            if not result.get("valid"):
                log.warning(f"重新验证暂时失败，仍处于离线宽限期: {result.get('msg')}")
            return True

        log.warning(f"重新验证失败，授权已暂停: {result.get('msg')}")
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
                self._apply_runtime_policy(result)
                if result.get("status") == "ok":
                    remaining = _coerce_non_negative_int(result.get("remaining_seconds"), 0)
                    with self._lock:
                        current = dict(self.last_verify_result or {})
                        current.update({
                            "valid": True,
                            "remaining_seconds": remaining,
                            "heartbeat_interval": self._heartbeat_interval,
                            "heartbeat_timeout": self._heartbeat_timeout,
                            "max_offline_seconds": self._max_offline_seconds,
                            "admin_contact": self._admin_contact,
                            "announcement": self._announcement,
                        })
                        if current.get("trial"):
                            current["trial_hours_left"] = remaining // 3600
                        else:
                            current["days_left"] = remaining // 86400
                        self.last_verify_result = current
                    self._mark_server_contact()
                    log.debug(f"心跳成功，剩余 {remaining}s")
                elif result.get("status") in ("expired", "banned", "disabled"):
                    with self._lock:
                        self._valid = False
                    self.last_verify_result = {
                        **(self.last_verify_result or {}),
                        "valid": False,
                        "msg": result.get("message", result.get("status")),
                    }
                    log.warning(f"心跳返回: {result.get('status')}")
                    break
                elif result.get("temporary_error") and self._within_offline_grace():
                    log.debug(f"心跳临时失败，仍处于离线宽限期: {result.get('message', '')}")
                    continue
                else:
                    with self._lock:
                        self._valid = False
                    self.last_verify_result = {
                        **(self.last_verify_result or {}),
                        "valid": False,
                        "msg": result.get("message", "心跳失败"),
                    }
                    log.warning(f"心跳失败，授权已暂停: {result.get('message', '未知错误')}")
                    break

        self._heartbeat_thread = threading.Thread(target=_loop, daemon=True, name="heartbeat")
        self._heartbeat_thread.start()
        log.info(f"心跳线程已启动，间隔 {self._heartbeat_interval}s")

    def stop_heartbeat(self):
        """停止心跳"""
        self._stop_heartbeat.set()
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=5)

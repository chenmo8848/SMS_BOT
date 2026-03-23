# -*- coding: utf-8 -*-
"""SMS Bot v6 — 配置管理（Pydantic 校验，启动即检查）"""

import os, json, sys, traceback
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator

# ─── 路径常量 ───
BOT_DIR     = os.path.dirname(os.path.abspath(__file__))
ROOT        = os.path.dirname(BOT_DIR)
CONFIG_FILE = os.path.join(ROOT, "config.json")
TASK_FILE   = os.path.join(ROOT, "tasks.json")
CRASH_LOG   = os.path.join(ROOT, "crash.log")
LOG_FILE    = os.path.join(ROOT, "sms_bot.log")
SCRIPTS_DIR = os.path.join(ROOT, "scripts")
SEND_PS1    = os.path.join(SCRIPTS_DIR, "send_sms.ps1")
CHECK_PS1   = os.path.join(SCRIPTS_DIR, "check_status.ps1")
RESTART_PS1 = os.path.join(SCRIPTS_DIR, "restart_phonelink.ps1")


def write_crash(msg: str):
    """紧急写入崩溃日志 — 即使 logging 未初始化也能工作"""
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(CRASH_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


class BotConfig(BaseModel):
    """全部配置项，启动时一次性校验类型和取值范围"""

    # ── 核心 ──
    bot_token: str
    allowed_user_ids: list[int]
    notify_user_id: int
    notify_group_id: Optional[int] = None
    proxy: Optional[str] = None

    # ── 发送 ──
    interval_min: int = Field(default=60, ge=5)
    interval_max: int = Field(default=90, ge=5)
    send_engine: str = Field(default="auto")

    # ── 监控 ──
    mon_status_sec: int = Field(default=30, ge=5)
    mon_sms_sec: int = Field(default=10, ge=3)

    # ── 日期格式 ──
    sms_date_sep: str = Field(default="/")
    user_date_fmt: str = Field(default="%Y-%m-%d")

    # ── 数据整理列配置 ──
    user_import_cols: list[str] = Field(
        default=["放款金额", "姓名", "身份证", "手机号码", "银行卡号", "放款日期"]
    )

    # ── 落地测试 ──
    test_enabled: bool = False
    test_phone: str = ""
    test_interval_min: int = Field(default=30, ge=1)
    test_content: str = "落地测试"

    # ── 授权（保留字段兼容旧配置，实际地址已内置）──
    license_api_url: str = Field(default="", description="已弃用")

    @field_validator("bot_token")
    @classmethod
    def check_token(cls, v):
        if not v or ":" not in v or len(v) < 20:
            raise ValueError("bot_token 格式不正确，应为 BotFather 提供的完整 Token")
        return v

    @field_validator("send_engine")
    @classmethod
    def check_engine(cls, v):
        if v not in ("auto", "uia", "sendkeys"):
            raise ValueError(f"send_engine 必须是 auto/uia/sendkeys，当前值: {v}")
        return v

    @field_validator("sms_date_sep")
    @classmethod
    def check_sep(cls, v):
        if v not in ("/", "-"):
            raise ValueError(f"sms_date_sep 只支持 / 或 -，当前值: {v}")
        return v

    @model_validator(mode="after")
    def check_interval_range(self):
        if self.interval_max < self.interval_min:
            raise ValueError(
                f"interval_max({self.interval_max}) 不能小于 interval_min({self.interval_min})"
            )
        return self


def load_config() -> BotConfig:
    """从 config.json 加载并校验，失败写崩溃日志后退出"""
    if not os.path.exists(CONFIG_FILE):
        write_crash(f"找不到 config.json: {CONFIG_FILE}\n请先运行 install")
        print("找不到 config.json，请先运行安装向导")
        sys.exit(1)
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            raw = json.load(f)
        if not raw.get("proxy"):
            raw["proxy"] = None
        if not raw.get("notify_group_id"):
            raw["notify_group_id"] = None
        return BotConfig(**raw)
    except json.JSONDecodeError as e:
        write_crash(f"config.json 格式错误: {e}")
        print(f"config.json JSON 解析失败: {e}")
        sys.exit(1)
    except Exception as e:
        write_crash(f"配置校验失败: {e}\n{traceback.format_exc()}")
        print(f"配置校验失败: {e}")
        sys.exit(1)


def save_config(cfg: BotConfig):
    """原子写入配置文件"""
    data = cfg.model_dump()
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, CONFIG_FILE)


def update_config(cfg: BotConfig, **kwargs) -> BotConfig:
    """更新指定配置项并保存，返回新配置对象"""
    data = cfg.model_dump()
    data.update(kwargs)
    new_cfg = BotConfig(**data)
    save_config(new_cfg)
    return new_cfg

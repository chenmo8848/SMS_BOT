# -*- coding: utf-8 -*-
"""SMS Bot v6 — 文本格式化工具"""

import random
import re


def md_escape(text: str) -> str:
    """转义用户内容中可能破坏 Markdown 解析的字符"""
    for ch in ["[", "]", "(", ")", "`"]:
        text = text.replace(ch, "\\" + ch)
    return text


def calc_eta(count: int, interval_min: int = 60, interval_max: int = 90) -> int:
    """根据剩余条数估算分钟数"""
    return max(1, int(count * (interval_min + interval_max) / 2 / 60))


def mask_phone(phone: str) -> str:
    """手机号脱敏：13800001234 → 138****1234"""
    p = phone.strip()
    if len(p) >= 7:
        return p[:3] + "****" + p[-4:]
    return p


def normalize_phone(p: str) -> str:
    """标准化手机号：去掉 +86 前缀、空格、横杠"""
    p = (p or "").strip().replace(" ", "").replace("-", "")
    if p.startswith("+86"):
        p = p[3:]
    if p.startswith("86") and len(p) == 13:
        p = p[2:]
    return p


def parse_phone_from_excel(v) -> str:
    """Excel 手机号标准化（处理 .0 后缀等）"""
    if v is None:
        return ""
    s = str(v).strip()
    if s.endswith(".0"):
        s = s[:-2]
    s = re.sub(r"[\s-]", "", s)
    if s.startswith("+86"):
        s = s[3:]
    if s.startswith("86") and len(s) == 13:
        s = s[2:]
    return s


def parse_amount(v) -> str:
    """金额处理：去掉小数位为整数"""
    if v is None:
        return ""
    if isinstance(v, (int, float)):
        return str(int(v)) if float(v) == int(float(v)) else str(round(v, 2))
    s = str(v).strip().replace(",", "").replace("，", "")
    s = re.sub(r"[¥￥$€]", "", s).strip()
    try:
        f = float(s)
        return str(int(f)) if f == int(f) else str(round(f, 2))
    except Exception:
        return s


def parse_date_for_sms(v, sep: str = "/") -> str:
    """短信模板用的日期解析，分隔符由 sep 控制"""
    if v is None:
        return ""
    if hasattr(v, "strftime"):
        return f"{v.year}{sep}{v.month:02d}{sep}{v.day:02d}"
    s = str(v).strip()
    if re.match(r"^\d{8}$", s):
        return f"{s[:4]}{sep}{int(s[4:6]):02d}{sep}{int(s[6:8]):02d}"
    if re.match(r"^\d{8}\.0$", s):
        return f"{s[:4]}{sep}{int(s[4:6]):02d}{sep}{int(s[6:8]):02d}"
    m = re.match(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
    if m:
        return f"{m.group(1)}{sep}{int(m.group(2)):02d}{sep}{int(m.group(3)):02d}"
    m = re.match(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", s)
    if m:
        return f"{m.group(3)}{sep}{int(m.group(1)):02d}{sep}{int(m.group(2)):02d}"
    return s


FISHING_QUOTES = [
    "🎣 开工大吉！祝老板今日鱼跃龙门，金币满盆",
    "🔥 火力全开！老板的渔船已驶向金银岛",
    "⚡ 老板驾到，各路鱼儿请自觉排队上钩",
    "🚀 引擎点火，满载金币出发！",
    "🎪 锣鼓喧天，捕鱼大赛正式开幕！",
    "🌊 捕鱼达人已就位，好运气正在派送中",
    "🍀 今日宜出海，诸事皆宜，大鱼必来",
    "🌅 海面风平浪静，是个丰收的好日子",
    "✨ 今日运势：五星爆发，逢投必中",
    "🧧 财神爷已上船，老板请放心出海",
    "🐟 深海金矿已炸开，请老板速来收网！",
    "💰 满屏金币爆不停，今日鱼情极佳",
    "🎰 全场爆率 200%！老板的专属炮台已归位",
    "🐠 海底宝藏雷达已开启，坐等大鱼上钩",
    "🎯 瞄准大鱼，一炮一个准！祝老板今日爆仓",
    "💎 深海探测到稀有鱼群，请求开炮许可！",
    "📡 声呐探测：前方大量鱼群聚集，建议全速前进",
    "🏆 祝老板今日满载而归，日进斗金",
    "👑 海上之王回来了！鱼儿们瑟瑟发抖",
    "🦈 老板一出手，鲨鱼都得绕道走",
    "💪 别人钓鱼靠运气，老板钓鱼靠实力",
    "🔱 三叉戟已就位，今日目标：清空鱼塘",
    "🏴‍☠️ 海盗旗升起！今日不空手而归",
    "🐙 章鱼哥来报到：老板今天想吃什么鱼？",
    "🎮 系统提示：您的欧气已充满，请开始游戏",
    "📦 快递通知：您的一箱金币正在派送中",
    "🍳 今日特供：红烧大鱼，清蒸金币，干炸好运",
    "🛸 外星鱼群入侵！请老板立即出击",
    "🎵 BGM已切换为《好运来》，请开始表演",
    "🐋 鲸鱼来电：听说老板今天要出海？我先跑了",
]


def fishing_quote() -> str:
    return random.choice(FISHING_QUOTES)

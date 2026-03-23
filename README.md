<div align="center">

# 🐟 SMS Bot v6

<img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
<img src="https://img.shields.io/badge/Telegram-Bot-26A5E4?style=for-the-badge&logo=telegram&logoColor=white" />
<img src="https://img.shields.io/badge/Windows-10%2F11-0078D6?style=for-the-badge&logo=windows&logoColor=white" />
<img src="https://img.shields.io/badge/Phone%20Link-Integrated-green?style=for-the-badge" />
<img src="https://img.shields.io/badge/License-Authorized-red?style=for-the-badge" />

<br/><br/>

**捕鱼达人 v6** — 基于 Telegram + Phone Link 的智能 SMS 自动化系统

<br/>

```
 ┌──────────────────────────────────────────────────────────┐
 │                                                          │
 │   🎣  "老板请上船"                                        │
 │                                                          │
 │   Telegram Bot  →  Windows Phone Link  →  SMS 发送       │
 │                                                          │
 │   批量导入 · 模板渲染 · 自动发送 · 落地测试 · 全程监控    │
 │                                                          │
 └──────────────────────────────────────────────────────────┘
```

</div>

---

## ✨ 核心功能

<table>
<tr>
<td width="50%">

### 📱 智能发送
- **双引擎切换** — UIA 自动化 + SendKeys 兜底
- **Auto 模式** — 自动选择最优引擎并缓存
- **DB 确认** — 读取 phone.db 验证发送成功
- **随机间隔** — 可配置发送间隔（5~90秒）
- **优先级队列** — 测试/回复 SMS 自动抢占

</td>
<td width="50%">

### 📊 任务管理
- **多组任务** — 支持多组队列排队执行
- **断点续传** — 异常重启自动恢复进度
- **暂停/继续** — 随时控制发送节奏
- **实时进度** — 进度条 + ETA + 成功率
- **结果导出** — 完成后自动生成报告文件

</td>
</tr>
<tr>
<td>

### 🔍 三层监控
- **进程监控** — Phone Link 运行状态检测
- **连接监控** — phone.db 更新频率分析
- **窗口监控** — 检测 App 假死冻结
- **自动恢复** — 异常时自动重启 Phone Link
- **状态通知** — 离线/恢复实时推送

</td>
<td>

### 📡 落地测试
- **定时测试** — 周期性发送测试短信
- **通道验证** — 确认 SMS 实际到达
- **优先抢占** — 测试期间自动暂停批量任务
- **灵活配置** — 自定义号码/内容/间隔

</td>
</tr>
</table>

---

## 🏗️ 系统架构

```
  ┌─────────────┐         ┌──────────────────┐
  │  Telegram    │◄───────►│   SMS Bot v6     │
  │  用户/群组    │  API    │   (Python)       │
  └─────────────┘         └───────┬──────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
    ┌─────────▼────────┐ ┌───────▼────────┐ ┌────────▼───────┐
    │  SmsSender        │ │ MonitorService │ │ LandTestService│
    │  UIA / SendKeys   │ │ 三层状态检测    │ │ 定时测试发送    │
    └────────┬─────────┘ └───────┬────────┘ └────────────────┘
             │                   │
    ┌────────▼─────────┐ ┌──────▼─────────┐
    │  Phone Link       │ │  phone.db      │
    │  (Windows App)    │ │  (SQLite)      │
    └────────┬─────────┘ └────────────────┘
             │
    ┌────────▼─────────┐
    │  手机 (蓝牙/WiFi) │
    │  实际发送 SMS      │
    └──────────────────┘

                    ┌──────────────────┐
                    │  Auth Server     │
                    │  授权验证 + 心跳   │
                    └──────────────────┘
```

---

## 🚀 快速开始

### 环境要求

| 项目 | 要求 |
|------|------|
| 系统 | Windows 10 / 11 |
| Python | 3.10+ |
| 应用 | Microsoft Phone Link（已连接手机） |
| 网络 | 可访问 Telegram API |

### 安装

```powershell
# 1. 克隆项目
git clone https://github.com/chenmo8848/SMS_BOT.git
cd SMS_BOT

# 2. 运行安装向导
python -m bot.setup

# 3. 启动 Bot
smsbot.bat
# 或
python -m bot
```

### 安装向导会引导你配置

- Telegram Bot Token（从 @BotFather 获取）
- 管理员用户 ID
- 发送间隔 / 引擎选择
- 落地测试配置

---

## 🎮 使用方式

### Telegram 命令

| 命令 | 说明 | 快捷操作 |
|------|------|---------|
| `/start` | 打开主菜单 | 按钮式操作面板 |
| `/send 号码 内容` | 单条发送 | 快速测试 |
| `/batch` | 批量导入 | 发送文本/文件 |
| `/template` | 模板管理 | 查看/编辑/预览 |
| `/status` | 发送进度 | 实时统计 |
| `/pause` / `/resume` | 暂停/继续 | 控制节奏 |
| `/stop` | 停止任务 | 紧急刹车 |
| `/settings` | 系统设置 | 在线调参 |
| `/activate` | 授权验证 | 重新验证 |
| `/activate 卡密` | 卡密激活 | 直接激活 |
| `/machine_id` | 查看机器码 | 用于购买授权 |

### 批量导入格式

**文本模式** — 直接发送：
```
13800138001 你好，这是测试消息
13900139002 另一条消息内容
```

**Excel 模式** — 上传 `.xlsx` 文件，配合模板自动渲染

**模板变量示例：**
```
{姓名}您好，您的{放款金额}元已于{放款日期}发放到尾号{银行卡号[-4:]}的账户。
```

---

## 🔐 授权系统

### 工作流程

```
首次启动 ──► 自动注册 ──► 24h 试用
                              │
              购买卡密 ◄──── 试用到期
                │
          /activate 卡密 ──► 正式授权 ──► 心跳保活
                                            │
                              到期提醒 ◄── 定期检查
```

### 授权特性

- **即开即用** — 新设备自动获得 24 小时免费试用
- **卡密激活** — `/activate RDP-XXXX-XXXX-XXXX-XXXX`
- **设备绑定** — 基于硬件指纹，一机一码
- **心跳保活** — 后台自动上报在线状态
- **离线容错** — 网络中断时使用本地缓存，不影响使用
- **到期提醒** — 7天、3天、1天自动 Telegram 通知

---

## 📁 项目结构

```
SMS_BOT/
├── bot/
│   ├── __main__.py              # 启动入口
│   ├── config.py                # 配置管理 (Pydantic)
│   ├── state.py                 # 全局状态机
│   ├── setup.py                 # 安装向导
│   ├── handlers/                # Telegram 命令处理
│   │   ├── register.py          #   处理器注册中心
│   │   ├── common.py            #   权限装饰器 + 工具
│   │   ├── menu.py              #   /start 主菜单
│   │   ├── send.py              #   /send /batch 发送
│   │   ├── task.py              #   任务调度 + 进度
│   │   ├── monitor.py           #   /monitor 监控
│   │   ├── settings.py          #   /settings 设置
│   │   ├── template.py          #   /template 模板
│   │   ├── data.py              #   Excel 数据处理
│   │   ├── license.py           #   /activate 授权
│   │   ├── landtest.py          #   落地测试
│   │   └── log_view.py          #   日志查看
│   ├── services/                # 核心服务
│   │   ├── sms_sender.py        #   SMS 发送引擎
│   │   ├── phone_db.py          #   Phone Link 数据库
│   │   ├── phone_link.py        #   进程管理
│   │   ├── monitor_svc.py       #   三层监控服务
│   │   ├── task_manager.py      #   任务持久化
│   │   ├── land_test_svc.py     #   落地测试服务
│   │   ├── license.py           #   授权验证 + 心跳
│   │   ├── notifier.py          #   Telegram 通知
│   │   └── excel_parser.py      #   Excel 解析
│   ├── models/                  # 数据模型
│   │   ├── sms.py               #   SMS / SIM 模型
│   │   └── task.py              #   任务 / 分组模型
│   └── utils/                   # 工具函数
│       ├── formatting.py        #   格式化 / 号码处理
│       ├── keyboard.py          #   按钮构建器
│       └── log_reader.py        #   日志读取
├── scripts/                     # PowerShell 脚本
│   ├── send_sms.ps1             #   SMS 发送脚本
│   ├── check_status.ps1         #   状态检查
│   ├── restart_phonelink.ps1    #   Phone Link 重启
│   └── manager.ps1              #   进程管理
├── config.json                  # 运行配置
├── smsbot.bat                   # 一键启动
└── 使用教程.txt                  # 使用说明
```

---

## ⚙️ 配置说明

`config.json` 核心配置项：

```jsonc
{
    "bot_token": "...",           // Telegram Bot Token
    "allowed_user_ids": [123],    // 授权用户 ID
    "notify_user_id": 123,        // 通知接收用户
    "interval_min": 60,           // 最小发送间隔（秒）
    "interval_max": 90,           // 最大发送间隔（秒）
    "send_engine": "auto",        // 发送引擎: auto/uia/sendkeys
    "mon_status_sec": 30,         // 状态监控频率
    "mon_sms_sec": 10,            // SMS 监控频率
    "test_enabled": false,        // 落地测试开关
    "test_phone": "",             // 测试号码
    "test_interval_min": 30       // 测试间隔（分钟）
}
```

---

<div align="center">

**SMS Bot v6** · 捕鱼达人 🐟

*Telegram · Phone Link · Windows*

</div>

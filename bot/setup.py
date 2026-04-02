# -*- coding: utf-8 -*-
"""
SMS Bot v6 安装向导
智能引擎检测（硬件→auto/sendkeys）、SOCKS5 代理支持、Pydantic 依赖
"""
import os, sys, json, platform, subprocess, struct, time, threading

ROOT        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(ROOT, "config.json")

os.system("")
GRN="\033[92m"; YLW="\033[93m"; CYN="\033[96m"
GRY="\033[90m"; RED="\033[91m"; BLD="\033[1m"; RST="\033[0m"

def cls(): os.system("cls")
def ok(t):   print(f"  {GRN}✅{RST}  {t}")
def fail(t): print(f"  {RED}❌{RST}  {t}")
def info(t): print(f"  {GRY}   {t}{RST}")
def warn(t): print(f"  {YLW}⚠️{RST}  {t}")
def section(t):
    print(f"\n  {CYN}{'─'*40}{RST}")
    print(f"  {BLD}{t}{RST}")
    print(f"  {CYN}{'─'*40}{RST}\n")
def flush():
    try:
        import msvcrt
        while msvcrt.kbhit(): msvcrt.getch()
    except: pass
def ask(prompt, default=""):
    flush()
    hint = f" {GRY}(默认: {default}){RST}" if default else ""
    sys.stdout.write(f"\n  {CYN}▸{RST} {BLD}{prompt}{RST}{hint}\n  {CYN}▸{RST} ")
    sys.stdout.flush()
    try: v = sys.stdin.readline().strip(); return v if v else default
    except: return default
def confirm(q):
    flush()
    sys.stdout.write(f"\n  {YLW}?{RST} {q} {GRY}[Y/n]{RST} ")
    sys.stdout.flush()
    try: v = sys.stdin.readline().strip().upper(); return v != "N"
    except: return True
def pause(m="按回车继续..."):
    flush()
    sys.stdout.write(f"\n  {GRY}{m}{RST} ")
    sys.stdout.flush()
    try: sys.stdin.readline()
    except: pass
def spinner(msg, fn, *a, **kw):
    frames = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
    res=[None]; err=[None]; done=[False]
    def run():
        try: res[0] = fn(*a, **kw)
        except Exception as e: err[0] = e
        finally: done[0] = True
    threading.Thread(target=run, daemon=True).start()
    i = 0
    while not done[0]:
        sys.stdout.write(f"\r  {CYN}{frames[i%len(frames)]}{RST}  {msg}   ")
        sys.stdout.flush(); time.sleep(0.08); i += 1
    sys.stdout.write("\r" + " "*60 + "\r"); sys.stdout.flush()
    if err[0]: raise err[0]
    return res[0]

def check_system():
    section("步骤 1/5 · 系统环境检测")
    v = sys.getwindowsversion(); arch = struct.calcsize("P") * 8; py_ver = sys.version.split()[0]
    checks = [
        ("操作系统", f"Windows {platform.release()} (build {v.build})", v.major >= 10),
        ("系统架构", f"{arch} 位", True),
        ("Python", py_ver, sys.version_info >= (3, 9)),
    ]
    try:
        import ctypes
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
        checks.append(("管理员权限", "是" if is_admin else "否（开机自启可能失败）", True))
    except: pass
    try:
        r = subprocess.run(["tasklist","/FI","IMAGENAME eq PhoneExperienceHost.exe"],
                           capture_output=True, text=True, timeout=5)
        pl = "PhoneExperienceHost" in r.stdout
        checks.append(("手机连接", "✅ 运行中" if pl else "未运行（安装后需打开）", True))
    except: checks.append(("手机连接", "检测失败", True))

    # 智能引擎（硬件）
    engine = "auto"; engine_reason = ""
    try:
        import psutil
        mem_gb = psutil.virtual_memory().total / (1024**3)
        cpu_count = psutil.cpu_count(logical=True) or 1
        checks.append(("内存", f"{mem_gb:.1f} GB", mem_gb >= 2))
        checks.append(("CPU 核心", f"{cpu_count} 核", cpu_count >= 2))
        if mem_gb < 4 or cpu_count < 2:
            engine = "sendkeys"
            reasons = []
            if mem_gb < 4: reasons.append(f"内存{mem_gb:.1f}GB<4GB")
            if cpu_count < 2: reasons.append(f"CPU{cpu_count}核<2核")
            engine_reason = "、".join(reasons) + " → 降级 SendKeys"
        else:
            engine_reason = f"内存{mem_gb:.1f}GB ✅ CPU{cpu_count}核 ✅ → 自动模式"
    except ImportError:
        engine = "auto"; engine_reason = "安装依赖后自动检测"
        checks.append(("硬件检测", "安装后生效", True))

    label = "自动（优先UIA，自动降级）" if engine == "auto" else "SendKeys（兼容模式）"
    checks.append(("发送引擎", label, True))

    all_ok = True
    for lbl, val, good in checks:
        icon = f"{GRN}✅{RST}" if good else f"{RED}❌{RST}"
        print(f"  {icon}  {lbl:<12} {GRY}{val}{RST}")
        if not good and lbl in ("操作系统", "Python"): all_ok = False
    if engine_reason: info(f"    引擎判断：{engine_reason}")
    print()
    if not all_ok:
        fail("系统要求不满足"); pause("按回车退出..."); sys.exit(1)
    ok("环境检测通过")
    return engine

def install_deps():
    section("步骤 2/5 · 安装依赖")
    vd = os.path.join(ROOT, "venv"); vpy = os.path.join(vd, "Scripts", "python.exe")
    pip = os.path.join(vd, "Scripts", "pip.exe")
    if not os.path.exists(vpy):
        print("  创建虚拟环境...")
        r = subprocess.run([sys.executable, "-m", "venv", vd], capture_output=True, text=True)
        if r.returncode != 0:
            fail("虚拟环境创建失败"); pause("按回车退出..."); sys.exit(1)
    ok("虚拟环境就绪")
    subprocess.run([vpy, "-m", "pip", "install", "--upgrade", "pip",
                    "--no-input", "--disable-pip-version-check", "-q"],
                   capture_output=True, timeout=120)
    pkgs = [
        ("python-telegram-bot[socks]", "Telegram + SOCKS5"),
        ("httpx",       "HTTP 客户端"),
        ("psutil",      "进程+硬件检测"),
        ("openpyxl",    "Excel 读写"),
        ("pydantic",    "配置校验"),
        ("pydantic-settings", "配置管理"),
    ]
    failed = []
    for i, (pkg, desc) in enumerate(pkgs, 1):
        print(f"\n  [{i}/{len(pkgs)}] {BLD}{pkg}{RST} {GRY}({desc}){RST}")
        try:
            r = subprocess.run([pip, "install", pkg, "--no-input", "--disable-pip-version-check"],
                               capture_output=True, text=True, timeout=300)
            ok(pkg) if r.returncode == 0 else (fail(f"{pkg} 失败"), failed.append(pkg))
        except: fail(f"{pkg} 异常"); failed.append(pkg)
    print()
    if failed: warn(f"失败：{', '.join(failed)}"); return False
    ok("全部依赖安装完成"); return True

def config_wizard():
    section("步骤 3/5 · 配置向导")
    old = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f: old = json.load(f)
            info("检测到已有配置，回车保留原值\n")
        except: pass

    # Token
    old_token = old.get("bot_token", "")
    print(f"  {BLD}▎ 1/4  Bot Token{RST}\n")
    info("Telegram 搜索 @BotFather → /newbot → 复制 Token")
    if old_token: info(f"当前：{old_token[:12]}···{old_token[-4:]}")
    while True:
        token = ask("粘贴 Bot Token", old_token or "")
        if not token: fail("不能为空"); continue
        if ":" not in token or len(token) < 20:
            fail(f"格式可能不对"); 
            if not confirm("仍然使用？"): continue
        ok(f"Token：{token[:12]}···{token[-4:]}"); break

    # User ID
    old_uid = old.get("notify_user_id", 0)
    print(f"\n  {BLD}▎ 2/4  Telegram User ID{RST}\n")
    info("Telegram 搜索 @userinfobot → 发任意消息 → 复制 Id")
    if old_uid: info(f"当前：{old_uid}")
    while True:
        s = ask("粘贴 User ID", str(old_uid) if old_uid else "")
        if not s: fail("不能为空"); continue
        if s.lstrip("-").isdigit(): uid = int(s); ok(f"User ID：{uid}"); break
        fail(f"必须是数字")

    # 代理（HTTP + SOCKS5）
    old_proxy = old.get("proxy", "")
    print(f"\n  {BLD}▎ 3/4  网络代理{RST}\n")
    info("国内需代理访问 Telegram，支持 HTTP 和 SOCKS5")
    if old_proxy: info(f"当前：{old_proxy}")
    print(f"\n  {CYN}1{RST}. HTTP（Clash Verge 等）")
    print(f"  {CYN}2{RST}. SOCKS5")
    print(f"  {CYN}3{RST}. 不用代理")
    proxy = None
    while True:
        pt = ask("选择 (1/2/3)", "3" if not old_proxy else "")
        if pt == "1":
            old_port = ""
            if old_proxy and "http" in old_proxy: old_port = old_proxy.rsplit(":", 1)[-1]
            port = ask("HTTP 端口（Clash Verge 默认 7897）", old_port)
            if port.isdigit() and 1 <= int(port) <= 65535:
                proxy = f"http://127.0.0.1:{port}"; ok(f"代理：{proxy}"); break
            fail(f"端口无效：{port}")
        elif pt == "2":
            old_s = old_proxy.replace("socks5://", "") if old_proxy and "socks" in old_proxy else ""
            addr = ask("SOCKS5 地址（127.0.0.1:1080 或 user:pass@host:port）", old_s)
            if addr and ":" in addr:
                proxy = f"socks5://{addr}"; ok(f"代理：{proxy}"); break
            fail("需包含地址和端口")
        elif pt in ("3", ""):
            proxy = None; ok("直连模式"); break
        else: fail("请输入 1、2 或 3")

    # 间隔
    old_imin, old_imax = old.get("interval_min", 60), old.get("interval_max", 90)
    print(f"\n  {BLD}▎ 4/4  发送间隔{RST}\n")
    info(f"批量发送随机等待（秒），建议 60-90")
    imin_s = ask("最小间隔", str(old_imin)); imax_s = ask("最大间隔", str(old_imax))
    try: imin = max(5, int(imin_s)); imax = max(imin, int(imax_s))
    except: imin, imax = old_imin, old_imax
    ok(f"发送间隔：{imin}–{imax} 秒")

    result = dict(old)
    result.update({"bot_token": token, "allowed_user_ids": [uid], "notify_user_id": uid,
                    "proxy": proxy, "interval_min": imin, "interval_max": imax})
    for k, v in [("mon_status_sec",30),("mon_sms_sec",10),("sms_date_sep","/"),
                  ("user_import_cols",["放款金额","姓名","身份证","手机号码","银行卡号","放款日期"]),
                  ("user_date_fmt","%Y-%m-%d"),("test_enabled",False),("test_phone",""),
                  ("test_interval_min",30),("test_content","落地测试"),("notify_group_id",None),
                  ]:
        result.setdefault(k, v)
    return result

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)
    ok("配置已保存")

def test_connection(cfg):
    section("步骤 4/5 · 测试 Telegram 连接")
    py = os.path.join(ROOT, "venv", "Scripts", "python.exe")
    px = f'"{cfg["proxy"]}"' if cfg.get("proxy") else "None"
    code = f"import httpx;r=httpx.get('https://api.telegram.org',timeout=10,proxy={px});print('OK' if r.status_code in [200,302] else 'FAIL')"
    try:
        r = spinner("连接 Telegram", subprocess.run, [py, "-c", code],
                    capture_output=True, text=True, timeout=20)
        if "OK" in r.stdout: ok("Telegram 连接成功"); return True
        fail("无法连接 Telegram")
        if cfg.get("proxy"): warn("请检查代理是否启动")
        else: warn("国内需要代理")
        return False
    except subprocess.TimeoutExpired: fail("连接超时"); return False
    except Exception as e: fail(f"异常：{e}"); return False

def register_autostart():
    section("步骤 5/5 · 注册开机自启")
    py = os.path.join(ROOT, "venv", "Scripts", "pythonw.exe")
    cmd = (f"$a=New-ScheduledTaskAction -Execute '{py}' "
           f"-Argument '-m bot' -WorkingDirectory '{ROOT}';"
           f"$t=New-ScheduledTaskTrigger -AtStartup;"
           f"$s=New-ScheduledTaskSettingsSet -ExecutionTimeLimit 0 "
           f"-RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 2);"
           f"Register-ScheduledTask -TaskName 'SMSBot' "
           f"-Action $a -Trigger $t -Settings $s -RunLevel Highest -Force")
    try:
        r = spinner("注册计划任务", subprocess.run,
                    ["powershell","-Command",cmd], capture_output=True, text=True, timeout=30)
        if r.returncode == 0: ok("开机自启已注册（SMSBot）")
        else: warn("注册失败（需管理员权限）")
    except Exception as e: warn(f"注册失败：{e}")

def main():
    cls()
    print(f"""
  {CYN}╔════════════════════════════════════════╗{RST}
  {CYN}║{RST}   🎣 {BLD}捕鱼达人 v6  安装向导{RST}           {CYN}║{RST}
  {CYN}║{RST}   {GRY}Telegram + Phone Link 短信自动化{RST}    {CYN}║{RST}
  {CYN}╚════════════════════════════════════════╝{RST}
""")
    try:
        engine = check_system()
        if not install_deps(): pause("按回车退出..."); sys.exit(1)
        # 重新检测硬件（psutil 现在装好了）
        if engine == "auto":
            try:
                import psutil
                mem = psutil.virtual_memory().total / (1024**3)
                cpu = psutil.cpu_count(logical=True) or 1
                if mem < 4 or cpu < 2: engine = "sendkeys"
            except: pass
        cfg = config_wizard(); cfg["send_engine"] = engine; save_config(cfg)
        conn_ok = test_connection(cfg); register_autostart()
        eng = {"auto":"自动（优先UIA）","sendkeys":"SendKeys（兼容）","uia":"UIA（精确）"}.get(engine, engine)
        px_type = "SOCKS5" if cfg.get("proxy","") and "socks" in cfg.get("proxy","") else "HTTP" if cfg.get("proxy") else ""
        cls()
        print(f"""
  {GRN}╔════════════════════════════════════════╗{RST}
  {GRN}║   🎉  安装完成！                       ║{RST}
  {GRN}╚════════════════════════════════════════╝{RST}

  Token      {cfg["bot_token"][:15]}···{cfg["bot_token"][-4:]}
  User ID    {cfg["notify_user_id"]}
  代理       {cfg.get("proxy") or "直连"} {f"({px_type})" if px_type else ""}
  间隔       {cfg["interval_min"]}–{cfg["interval_max"]} 秒
  引擎       {eng}
  Telegram   {"✅ 可连接" if conn_ok else "❌ 连接失败"}

  {BLD}下一步：{RST}Telegram 找到 Bot → /start
""")
        if confirm("现在启动 Bot？"):
            py = os.path.join(ROOT, "venv", "Scripts", "pythonw.exe")
            os.chdir(ROOT); subprocess.Popen([py, "-m", "bot"])
            print(f"\n  {GRN}✅ Bot 已在后台启动{RST}\n  {GRY}请在 Telegram 查看通知{RST}\n")
        pause()
    except KeyboardInterrupt: print(f"\n\n  {YLW}安装已取消{RST}\n")
    except Exception as e:
        import traceback; print(f"\n  {RED}安装出错：{e}{RST}\n"); traceback.print_exc()
        pause("按回车退出..."); sys.exit(1)

if __name__ == "__main__": main()

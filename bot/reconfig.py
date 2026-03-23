# -*- coding: utf-8 -*-
"""SMS Bot v6 重新配置工具"""
import os, sys, json, subprocess, time

ROOT        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(ROOT, "config.json")

os.system("")
GRN="\033[92m"; YLW="\033[93m"; CYN="\033[96m"
GRY="\033[90m"; RED="\033[91m"; BLD="\033[1m"; RST="\033[0m"

def flush():
    try:
        import msvcrt
        while msvcrt.kbhit(): msvcrt.getch()
    except: pass
def ask(p, d=""):
    flush()
    hint = f" {GRY}(当前: {d}){RST}" if d else ""
    sys.stdout.write(f"\n  {CYN}▸{RST} {BLD}{p}{RST}{hint}\n  {CYN}▸{RST} ")
    sys.stdout.flush()
    try: v = sys.stdin.readline().strip(); return v if v else d
    except: return d

def main():
    os.system("cls")
    print(f"""
  {CYN}╔════════════════════════════════════╗{RST}
  {CYN}║{RST}   ⚙️  {BLD}捕鱼达人 v6  修改配置{RST}      {CYN}║{RST}
  {CYN}╚════════════════════════════════════╝{RST}
""")
    if not os.path.exists(CONFIG_FILE):
        print(f"  {RED}❌ 找不到 config.json{RST}\n  {GRY}请先运行安装向导{RST}")
        input("\n  按回车退出..."); return

    with open(CONFIG_FILE, encoding="utf-8") as f: cfg = json.load(f)

    proxy_display = cfg.get("proxy") or "直连"
    print(f"  {BLD}当前配置{RST}")
    print(f"  ─────────────────────────")
    print(f"  Token      {cfg['bot_token'][:15]}···{cfg['bot_token'][-4:]}")
    print(f"  User ID    {cfg['notify_user_id']}")
    print(f"  代理       {proxy_display}")
    print(f"  发送间隔   {cfg.get('interval_min',60)}–{cfg.get('interval_max',90)} 秒")
    print(f"  引擎       {cfg.get('send_engine','auto')}")
    print(f"  群组通知   {cfg.get('notify_group_id') or '未设置'}")
    print(f"\n  {GRY}直接回车 = 保持不变{RST}")

    v = ask("新 Bot Token", "")
    if v: cfg["bot_token"] = v

    v = ask("新 User ID", "")
    if v and v.lstrip("-").isdigit():
        cfg["allowed_user_ids"] = [int(v)]; cfg["notify_user_id"] = int(v)

    # 代理（支持 HTTP + SOCKS5）
    v = ask("代理（http://.. 或 socks5://.. 或 0=直连）", "")
    if v == "0": cfg["proxy"] = None
    elif v and ("://" in v): cfg["proxy"] = v
    elif v and v.isdigit(): cfg["proxy"] = f"http://127.0.0.1:{v}"

    v = ask("最小间隔秒数", "")
    if v and v.isdigit(): cfg["interval_min"] = max(5, int(v))

    v = ask("最大间隔秒数", "")
    if v and v.isdigit(): cfg["interval_max"] = max(cfg.get("interval_min", 5), int(v))

    v = ask("引擎 (auto/uia/sendkeys)", "")
    if v in ("auto", "uia", "sendkeys"): cfg["send_engine"] = v

    v = ask("群组通知 ID（0=关闭）", "")
    if v == "0": cfg["notify_group_id"] = None
    elif v and v.lstrip("-").isdigit(): cfg["notify_group_id"] = int(v)

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)
    print(f"\n  {GRN}✅ 配置已保存{RST}")

    flush()
    sys.stdout.write(f"\n  {YLW}?{RST} 重启 Bot 使配置生效？ {GRY}[Y/n]{RST} ")
    sys.stdout.flush()
    try: ans = sys.stdin.readline().strip().upper()
    except: ans = "N"

    if ans != "N":
        # 停止旧进程
        procs_to_kill = ["pythonw.exe"]
        for name in procs_to_kill:
            subprocess.run(["taskkill","/F","/IM",name], capture_output=True)
        time.sleep(2)
        py = os.path.join(ROOT, "venv", "Scripts", "pythonw.exe")
        if os.path.exists(py):
            subprocess.Popen([py, "-m", "bot"], cwd=ROOT)
            print(f"  {GRN}✅ Bot 已重启{RST}")
        else:
            print(f"  {RED}❌ 找不到 pythonw.exe，请手动启动{RST}")

    input("\n  按回车退出...")

if __name__ == "__main__": main()

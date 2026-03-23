# -*- coding: utf-8 -*-
"""Python 3.11 自动下载安装工具"""
import os, sys, struct, subprocess, urllib.request

os.system("")
GRN="\033[92m"; YLW="\033[93m"; CYN="\033[96m"
GRY="\033[90m"; RED="\033[91m"; BLD="\033[1m"; RST="\033[0m"

def progress(block, block_size, total):
    done = block * block_size
    if total > 0:
        p   = min(int(done / total * 30), 30)
        bar = f"{GRN}{'█'*p}{GRY}{'░'*(30-p)}{RST}"
        sys.stdout.write(f"\r  [{bar}]  {done/1024/1024:.1f}/{total/1024/1024:.1f} MB  ")
        sys.stdout.flush()

def main():
    os.system("cls")
    print(f"\n  {CYN}╔══════════════════════════════════╗{RST}")
    print(f"  {CYN}║{RST}  🐍 {BLD}Python 3.11 自动安装工具{RST}     {CYN}║{RST}")
    print(f"  {CYN}╚══════════════════════════════════╝{RST}\n")

    # 检测是否已安装
    try:
        r = subprocess.run(["python","--version"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and "3." in r.stdout:
            print(f"  {GRN}✅{RST}  已安装：{r.stdout.strip()}")
            print(f"  {GRY}无需重新安装，直接运行安装向导即可{RST}")
            input("\n  按回车退出...")
            return
    except: pass

    arch = struct.calcsize("P") * 8
    url  = (
        "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
        if arch == 64 else
        "https://www.python.org/ftp/python/3.11.9/python-3.11.9.exe"
    )
    save = os.path.join(os.environ.get("TEMP","C:\\Temp"), "python-3.11.9.exe")
    print(f"  系统架构：{arch} 位")
    print(f"  {GRY}下载地址：{url}{RST}\n")

    downloaded = False

    # 方法 1：urllib
    print("  📥 方法一：urllib 下载...")
    try:
        urllib.request.urlretrieve(url, save, progress)
        print()
        if os.path.exists(save) and os.path.getsize(save) > 1_000_000:
            downloaded = True
            print(f"  {GRN}✅{RST}  下载完成：{os.path.getsize(save)//1024//1024} MB")
    except Exception as e:
        print(f"\n  {YLW}⚠️{RST}  urllib 失败：{e}")

    # 方法 2：PowerShell
    if not downloaded:
        print("\n  📥 方法二：PowerShell 下载...")
        try:
            r = subprocess.run(
                ["powershell","-Command",
                 f"[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;"
                 f"(New-Object Net.WebClient).DownloadFile('{url}','{save}')"],
                capture_output=True, text=True, timeout=300
            )
            if os.path.exists(save) and os.path.getsize(save) > 1_000_000:
                downloaded = True
                print(f"  {GRN}✅{RST}  下载完成")
            else:
                print(f"  {YLW}⚠️{RST}  PowerShell 下载失败")
        except Exception as e:
            print(f"  {YLW}⚠️{RST}  PowerShell 失败：{e}")

    if not downloaded:
        print(f"\n  {RED}❌{RST}  所有下载方式均失败")
        print(f"  {GRY}请手动下载：{RST}")
        print(f"  {url}")
        print(f"\n  {YLW}⚠️  安装时务必勾选底部：[x] Add Python to PATH{RST}")
        input("\n  按回车退出...")
        return

    # 安装
    print("\n  📦 开始安装（静默模式）...")
    try:
        r = subprocess.run(
            [save, "/quiet", "InstallAllUsers=1", "PrependPath=1", "Include_test=0"],
            timeout=300
        )
        if r.returncode != 0:
            print(f"  {YLW}⚠️{RST}  静默安装失败，弹出安装界面...")
            print(f"  {YLW}⚠️  请务必勾选底部：[x] Add Python to PATH{RST}")
            subprocess.run([save, "InstallAllUsers=1", "PrependPath=1"], timeout=600)
    except subprocess.TimeoutExpired:
        print(f"  {YLW}⚠️{RST}  安装超时")
    except Exception as e:
        print(f"  {RED}❌{RST}  安装异常：{e}")

    print(f"\n  {GRN}✅ 安装完成{RST}")
    print(f"  {YLW}⚠️  请关闭此窗口后重新打开 smsbot.bat{RST}")
    print(f"  {GRY}确保 Python 环境变量生效{RST}")
    input("\n  按回车退出...")

if __name__ == "__main__":
    main()

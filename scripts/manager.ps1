# manager.ps1 - SMS Bot v6 管理菜单
# 由 smsbot.bat 调用（已设置 chcp 65001）

# ── 强制 UTF-8 输出 ──
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding  = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ErrorActionPreference = "SilentlyContinue"

# ── 路径 ──
$ROOT = Split-Path -Parent $PSScriptRoot
if (-not $ROOT) { $ROOT = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path) }

$VENV_PY  = Join-Path $ROOT "venv\Scripts\python.exe"
$VENV_PYW = Join-Path $ROOT "venv\Scripts\pythonw.exe"
$BOT_MOD  = "bot"
$CONFIG   = Join-Path $ROOT "config.json"
$LOG_FILE = Join-Path $ROOT "sms_bot.log"
$CRASH    = Join-Path $ROOT "crash.log"
$MGR_LOG  = Join-Path $ROOT "manager.log"

function Log($action, $result) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $MGR_LOG -Value "[$ts] $action : $result" -Encoding UTF8
}

function Show-Status {
    $running = $false
    $procs = Get-Process -Name "pythonw" -ErrorAction SilentlyContinue
    if ($procs) {
        foreach ($p in $procs) {
            try {
                $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($p.Id)").CommandLine
                if ($cmd -and $cmd -match "bot") { $running = $true; break }
            } catch {}
        }
    }
    if ($running) {
        Write-Host "  " -NoNewline
        Write-Host "[运行中]" -ForegroundColor Green
    } else {
        Write-Host "  " -NoNewline
        Write-Host "[已停止]" -ForegroundColor Red
    }
    return $running
}

function Do-Install {
    Write-Host ""
    # 检测 Python
    $py = $null
    foreach ($cmd in @("python", "python3", "py")) {
        try {
            $ver = & $cmd --version 2>&1
            if ($ver -match "Python 3\.(\d+)") {
                if ([int]$Matches[1] -ge 9) { $py = $cmd; break }
            }
        } catch {}
    }
    if (-not $py) {
        Write-Host "  Python 3.9+ 未找到" -ForegroundColor Red
        Write-Host "  请下载安装: https://www.python.org/downloads/"
        Write-Host "  安装时勾选 [x] Add Python to PATH"
        Log "INSTALL" "FAIL:no python"
        return
    }
    Write-Host "  Python: $py" -ForegroundColor Green

    # 创建虚拟环境
    if (-not (Test-Path $VENV_PY)) {
        Write-Host "  正在创建虚拟环境..."
        & $py -m venv (Join-Path $ROOT "venv")
        if (-not (Test-Path $VENV_PY)) {
            Write-Host "  创建失败" -ForegroundColor Red
            Log "INSTALL" "FAIL:venv"
            return
        }
    }
    Write-Host "  虚拟环境就绪" -ForegroundColor Green

    # 安装依赖
    Write-Host "  正在安装依赖..."
    $pip = Join-Path $ROOT "venv\Scripts\pip.exe"
    & $VENV_PY -m pip install --upgrade pip --no-input --disable-pip-version-check -q 2>&1 | Out-Null
    $deps = @(
        "python-telegram-bot[socks]",
        "httpx",
        "psutil",
        "openpyxl",
        "pydantic",
        "pydantic-settings"
    )
    foreach ($pkg in $deps) {
        Write-Host "    $pkg ... " -NoNewline
        $r = & $pip install $pkg --no-input --disable-pip-version-check -q 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "OK" -ForegroundColor Green
        } else {
            Write-Host "失败" -ForegroundColor Red
        }
    }

    # 运行安装向导
    Write-Host ""
    Write-Host "  启动安装向导..." -ForegroundColor Cyan
    & $VENV_PY (Join-Path $ROOT "bot\setup.py")
    Log "INSTALL" "OK"
}

function Do-Start {
    $running = Show-Status
    if ($running) {
        Write-Host "  已在运行中" -ForegroundColor Yellow
        Log "START" "SKIP:already running"
        return
    }
    if (-not (Test-Path $CONFIG)) {
        Write-Host "  尚未安装，请先选择 1 安装" -ForegroundColor Red
        Log "START" "FAIL:no config"
        return
    }
    if (-not (Test-Path $VENV_PYW)) {
        Write-Host "  尚未安装，请先选择 1 安装" -ForegroundColor Red
        Log "START" "FAIL:no venv"
        return
    }
    Start-Process -FilePath $VENV_PYW -ArgumentList "-m", $BOT_MOD -WorkingDirectory $ROOT -WindowStyle Hidden
    Write-Host "  已启动，请在 Telegram 查看通知" -ForegroundColor Green
    Log "START" "OK"
}

function Do-Stop {
    $stopped = $false
    $procs = Get-Process -Name "pythonw" -ErrorAction SilentlyContinue
    foreach ($p in $procs) {
        try {
            $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($p.Id)").CommandLine
            if ($cmd -and $cmd -match "bot") {
                Stop-Process -Id $p.Id -Force
                $stopped = $true
            }
        } catch {}
    }
    if ($stopped) {
        Write-Host "  已停止" -ForegroundColor Green
        Log "STOP" "OK"
    } else {
        Write-Host "  当前未运行" -ForegroundColor Yellow
        Log "STOP" "SKIP:not running"
    }
}

function Do-Uninstall {
    Write-Host ""
    Write-Host "  即将执行:" -ForegroundColor Yellow
    Write-Host "    - 停止 Bot"
    Write-Host "    - 删除开机自启任务"
    Write-Host "    - 删除虚拟环境"
    Write-Host ""
    $confirm = Read-Host "  确认卸载? (y/N)"
    if ($confirm -ne "y" -and $confirm -ne "Y") {
        Write-Host "  已取消"
        return
    }
    Do-Stop
    Unregister-ScheduledTask -TaskName "SMSBot" -Confirm:$false -ErrorAction SilentlyContinue
    if (Test-Path (Join-Path $ROOT "venv")) {
        Remove-Item -Path (Join-Path $ROOT "venv") -Recurse -Force
    }
    Write-Host "  卸载完成" -ForegroundColor Green
    Log "UNINSTALL" "OK"
}

# ── 主菜单 ──

while ($true) {
    Clear-Host
    Write-Host ""
    Write-Host "  ============================" -ForegroundColor Cyan
    Write-Host "      SMS Bot v6  管理菜单" -ForegroundColor Cyan
    Write-Host "  ============================" -ForegroundColor Cyan
    Write-Host ""
    $running = Show-Status
    Write-Host ""
    Write-Host "  1. 安装        " -NoNewline; Write-Host "(首次使用)" -ForegroundColor DarkGray
    Write-Host "  2. 启动        " -NoNewline; Write-Host "(后台运行)" -ForegroundColor DarkGray
    Write-Host "  3. 停止"
    Write-Host "  4. 重启"
    Write-Host "  5. 卸载"
    Write-Host ""
    Write-Host "  0. 退出"
    Write-Host ""
    $choice = Read-Host "  请选择"

    switch ($choice) {
        "1" { Do-Install; Read-Host "`n  按回车返回菜单" }
        "2" { Do-Start; Read-Host "`n  按回车返回菜单" }
        "3" { Do-Stop; Read-Host "`n  按回车返回菜单" }
        "4" { Do-Stop; Start-Sleep 2; Do-Start; Read-Host "`n  按回车返回菜单" }
        "5" { Do-Uninstall; Read-Host "`n  按回车返回菜单" }
        "0" { exit }
    }
}

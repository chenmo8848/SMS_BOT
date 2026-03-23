# send_sms.ps1 - Send SMS via Phone Link
# Engine selected by config (detected during install, switchable in settings)
# Usage: powershell -File send_sms.ps1 "phone" "message" "uia|sendkeys"

param(
    [Parameter(Position=0, Mandatory=$true)] [string]$Phone,
    [Parameter(Position=1, Mandatory=$true)] [string]$Message,
    [Parameter(Position=2)] [string]$Engine = "sendkeys"
)

Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WinAPI {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
    [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool attach);
    [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
}
"@

function Log($msg) { Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $msg" }

function Normalize-Phone([string]$p) {
    $p = $p.Trim().Replace(" ", "").Replace("-", "")
    if ($p.StartsWith("+86")) { $p = $p.Substring(3) }
    elseif ($p.StartsWith("86") -and $p.Length -eq 13) { $p = $p.Substring(2) }
    return $p
}

function Focus-Window([IntPtr]$hwnd) {
    $tid = [WinAPI]::GetCurrentThreadId()
    $pid2 = [uint32]0
    $tgt = [WinAPI]::GetWindowThreadProcessId($hwnd, [ref]$pid2)
    try {
        [WinAPI]::AttachThreadInput($tid, $tgt, $true) | Out-Null
        [WinAPI]::ShowWindow($hwnd, 9) | Out-Null
        [WinAPI]::SetForegroundWindow($hwnd) | Out-Null
    } finally {
        [WinAPI]::AttachThreadInput($tid, $tgt, $false) | Out-Null
    }
    Start-Sleep -Milliseconds 400
}

function Safe-Paste([string]$text) {
    for ($i = 0; $i -lt 3; $i++) {
        try {
            [System.Windows.Forms.Clipboard]::SetText($text)
            Start-Sleep -Milliseconds 200
            if ([System.Windows.Forms.Clipboard]::GetText() -eq $text) { break }
        } catch { Start-Sleep -Milliseconds 300 }
    }
    [System.Windows.Forms.SendKeys]::SendWait("^v")
    Start-Sleep -Milliseconds 400
}

function Reset-UI([IntPtr]$hwnd) {
    Focus-Window $hwnd
    for ($i = 0; $i -lt 3; $i++) {
        [System.Windows.Forms.SendKeys]::SendWait("{ESC}")
        Start-Sleep -Milliseconds 200
    }
    Start-Sleep -Milliseconds 300
}

# ═════════════════════════════════════
#  UIA helpers (only loaded if Engine=uia)
# ═════════════════════════════════════

function UIA-FindById($parent, [string]$id, [bool]$deep = $false) {
    $scope = if ($deep) {
        [System.Windows.Automation.TreeScope]::Descendants
    } else {
        [System.Windows.Automation.TreeScope]::Children
    }
    $cond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::AutomationIdProperty, $id)
    return $parent.FindFirst($scope, $cond)
}

function UIA-FindByClass($parent, [string]$cls) {
    $cond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ClassNameProperty, $cls)
    return $parent.FindFirst(
        [System.Windows.Automation.TreeScope]::Descendants, $cond)
}

function UIA-SetValue($elem, [string]$text) {
    try {
        $vp = $elem.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
        $vp.SetValue($text)
        return $true
    } catch { return $false }
}

function UIA-Invoke($elem) {
    try {
        $ip = $elem.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
        $ip.Invoke()
        return $true
    } catch { return $false }
}

# ═════════════════════════════════════
#  SendKeys path (verified by screenshots)
# ═════════════════════════════════════

function Send-ViaSendKeys {
    Log "1 Reset"
    Reset-UI $hwnd

    Log "2 New message"
    Focus-Window $hwnd
    [System.Windows.Forms.SendKeys]::SendWait("^1")
    Start-Sleep -Milliseconds 800
    Focus-Window $hwnd
    [System.Windows.Forms.SendKeys]::SendWait("^n")
    Start-Sleep -Milliseconds 2000

    Log "3 Phone"
    Focus-Window $hwnd
    [System.Windows.Forms.SendKeys]::SendWait("^a")
    Start-Sleep -Milliseconds 100
    [System.Windows.Forms.SendKeys]::SendWait("{DELETE}")
    Start-Sleep -Milliseconds 100
    Safe-Paste $Phone

    Log "4 Confirm"
    Start-Sleep -Milliseconds 800
    [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
    Start-Sleep -Milliseconds 2500

    Log "5 Tab Tab"
    Focus-Window $hwnd
    [System.Windows.Forms.SendKeys]::SendWait("{TAB}")
    Start-Sleep -Milliseconds 500
    [System.Windows.Forms.SendKeys]::SendWait("{TAB}")
    Start-Sleep -Milliseconds 500

    Log "6 Message"
    Safe-Paste $Message

    Log "7 Send"
    Start-Sleep -Milliseconds 300
    [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
    Start-Sleep -Milliseconds 1500
}

# ═════════════════════════════════════
#  UIA path (targeted navigation, avoids message list)
# ═════════════════════════════════════

function Send-ViaUIA {
    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $win = $root.FindFirst(
        [System.Windows.Automation.TreeScope]::Children,
        (New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $app.Id)))
    if (-not $win) { throw "Window not in UIA tree" }

    $site = UIA-FindByClass $win "InputSiteWindowClass"
    if (-not $site) { throw "InputSiteWindowClass not found" }

    $convList = UIA-FindById $site "ConversationList"
    $convPane = UIA-FindById $site "ConversationPane"
    if (-not $convList -or -not $convPane) { throw "Containers not found" }

    Log "1 NewMessageButton"
    $newBtn = UIA-FindById $convList "NewMessageButton" $true
    if (-not $newBtn) { throw "NewMessageButton not found" }
    UIA-Invoke $newBtn | Out-Null
    Start-Sleep -Milliseconds 2000

    Log "2 Recipient (ValuePattern)"
    $suggestBox = UIA-FindById $convPane "ContactSuggestionsBox"
    $toField = if ($suggestBox) { UIA-FindById $suggestBox "TextBox" } else { $null }
    if (-not $toField) { throw "Recipient field not found" }
    if (-not (UIA-SetValue $toField $Phone)) { throw "SetValue failed on recipient" }

    Log "3 Confirm (Enter)"
    Start-Sleep -Milliseconds 800
    $toField.SetFocus()
    Start-Sleep -Milliseconds 200
    [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
    Start-Sleep -Milliseconds 3000

    Log "4 Message"
    $msgField = UIA-FindById $convPane "InputTextBox" $true
    if (-not $msgField) { throw "InputTextBox not found" }
    UIA-SetValue $msgField $Message | Out-Null

    Start-Sleep -Milliseconds 500
    $sendBtn = UIA-FindById $convPane "SendMessageButton"
    if ($sendBtn -and -not $sendBtn.Current.IsEnabled) {
        Log "  Button disabled, retrying with paste"
        $msgField.SetFocus()
        Start-Sleep -Milliseconds 300
        [System.Windows.Forms.SendKeys]::SendWait("^a{DELETE}")
        Start-Sleep -Milliseconds 100
        Safe-Paste $Message
        Start-Sleep -Milliseconds 500
    }

    Log "5 Send"
    if ($sendBtn) {
        for ($i = 0; $i -lt 10; $i++) {
            if ($sendBtn.Current.IsEnabled) { break }
            Start-Sleep -Milliseconds 500
        }
        if ($sendBtn.Current.IsEnabled) {
            UIA-Invoke $sendBtn | Out-Null
            Log "  InvokePattern OK"
        } else {
            $msgField.SetFocus()
            [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
            Log "  Enter fallback"
        }
    } else {
        [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
    }
    Start-Sleep -Milliseconds 1500
}

# ═════════════════════════════════════
#  Main
# ═════════════════════════════════════

$Phone = Normalize-Phone $Phone
Log "To: $Phone | Engine: $Engine"

$app = Get-Process | Where-Object {
    $_.ProcessName -like "*PhoneExperience*" -and $_.MainWindowTitle -ne ""
} | Select-Object -First 1

if (-not $app) { Write-Host "FAIL: Phone Link not running"; exit 1 }
$hwnd = $app.MainWindowHandle
if ($hwnd -eq [IntPtr]::Zero) { Write-Host "FAIL: No window handle"; exit 1 }

# Load UIA assemblies if needed (uia or auto mode)
$UseUIA = $false
if ($Engine -eq "uia" -or $Engine -eq "auto") {
    try {
        Add-Type -AssemblyName UIAutomationClient  -ErrorAction Stop
        Add-Type -AssemblyName UIAutomationTypes   -ErrorAction Stop
        $UseUIA = $true
    } catch {
        Log "UIA load failed, using SendKeys"
        $UseUIA = $false
    }
}

try {
    if ($UseUIA) {
        try {
            Send-ViaUIA
            Log "OK [UIA]"
            Write-Host "OK [UIA]"
        } catch {
            Log "UIA error: $_ - falling back to SendKeys"
            Send-ViaSendKeys
            Log "OK [SendKeys fallback]"
            Write-Host "OK [SendKeys fallback]"
        }
    } else {
        Send-ViaSendKeys
        Log "OK [SendKeys]"
        Write-Host "OK [SendKeys]"
    }

} catch {
    Log "ERROR: $_"
    Write-Host "FAIL: $_"
    exit 1

} finally {
    try {
        Start-Sleep -Milliseconds 500
        Reset-UI $hwnd
    } catch {}
}

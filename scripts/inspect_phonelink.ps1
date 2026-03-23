# inspect_phonelink.ps1
# Lightweight scan: one flat FindAll, no recursion, won't freeze Phone Link.
# Run with Phone Link open on the Messages tab.
#
# Usage: powershell -ExecutionPolicy Bypass -File inspect_phonelink.ps1

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$outFile = Join-Path $PSScriptRoot "phonelink_tree.txt"

$proc = Get-Process | Where-Object {
    $_.ProcessName -like "*PhoneExperience*" -and $_.MainWindowTitle -ne ""
} | Select-Object -First 1

if (-not $proc) {
    Write-Host "Phone Link is not running."
    exit 1
}

Write-Host "Found: PID=$($proc.Id) Title='$($proc.MainWindowTitle)'"

$root = [System.Windows.Automation.AutomationElement]::RootElement
$cond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $proc.Id)
$win = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $cond)

if (-not $win) {
    Write-Host "Window not found in UIA tree."
    exit 1
}

Write-Host "Scanning (flat, ~5 seconds)..."

# Single flat scan — no recursion
$all = $win.FindAll(
    [System.Windows.Automation.TreeScope]::Descendants,
    [System.Windows.Automation.Condition]::TrueCondition)

$lines = @()
$lines += "Phone Link UIA Scan"
$lines += "Date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$lines += "PID: $($proc.Id)  Window: $($proc.MainWindowTitle)"
$lines += "Elements: $($all.Count)"
$lines += ""
$lines += "Type | Name | AutomationId | Class | Enabled | Focusable"
$lines += "---- | ---- | ------------ | ----- | ------- | ---------"

foreach ($e in $all) {
    try {
        $type = $e.Current.ControlType.ProgrammaticName -replace 'ControlType\.', ''
        $name = $e.Current.Name
        $id   = $e.Current.AutomationId
        $cls  = $e.Current.ClassName
        $en   = $e.Current.IsEnabled
        $foc  = $e.Current.IsKeyboardFocusable

        # Only log interesting elements (skip empty unnamed containers)
        if ($name -or $id -or $type -in @('Edit','Button','ListItem','Text','ComboBox','CheckBox')) {
            $lines += "$type | $name | $id | $cls | $en | $foc"
        }
    } catch {}
}

$lines | Out-File -FilePath $outFile -Encoding UTF8
Write-Host "Done. $($all.Count) elements, saved to:"
Write-Host $outFile

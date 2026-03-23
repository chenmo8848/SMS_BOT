# restart_phonelink.ps1
# Kill all Phone Link processes and restart
# Outputs to stdout: OK / FAIL

$PROCS = @("PhoneExperienceHost","YourPhone","YourPhoneServer","YourPhoneAppProxy")

function Log($msg) { Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $msg" }

# Step 1: Kill all related processes
Log "Killing Phone Link processes..."
foreach ($name in $PROCS) {
    Get-Process -Name $name -ErrorAction SilentlyContinue | ForEach-Object {
        Log "  Kill $($_.ProcessName) PID $($_.Id)"
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
}

# Step 2: Wait up to 10s for all to exit
Log "Waiting for processes to exit..."
$t = (Get-Date).AddSeconds(10)
while ((Get-Date) -lt $t) {
    $found = $false
    foreach ($name in $PROCS) {
        if (Get-Process -Name $name -ErrorAction SilentlyContinue) {
            $found = $true; break
        }
    }
    if (-not $found) { break }
    Start-Sleep -Milliseconds 500
}
Start-Sleep -Seconds 1

# Step 3: Launch Phone Link
Log "Launching Phone Link..."
$launched = $false

# Method 1: AppxPackage with manifest AppId
$pkg = Get-AppxPackage -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -like "*YourPhone*" -or $_.Name -like "*PhoneLink*"
} | Select-Object -First 1

if ($pkg) {
    Log "  Package: $($pkg.PackageFullName)"
    try {
        $manifest = Get-AppxPackageManifest -Package $pkg.PackageFullName -ErrorAction Stop
        $appEntry = $manifest.Package.Applications.Application | Select-Object -First 1
        $appId = $appEntry.Id
        $fullId = $pkg.PackageFamilyName + "!" + $appId
        Log "  Launching AppID: $fullId"
        Start-Process "explorer.exe" -ArgumentList "shell:AppsFolder\$fullId"
        $launched = $true
    } catch {
        Log "  Manifest failed: $_"
        # Try common AppIDs
        foreach ($id in @("App", "PhoneExperienceHost")) {
            $fullId = $pkg.PackageFamilyName + "!" + $id
            Log "  Trying AppID: $fullId"
            Start-Process "explorer.exe" -ArgumentList "shell:AppsFolder\$fullId"
        }
        $launched = $true
    }
}

# Method 2: URI fallback
if (-not $launched) {
    Log "  URI fallback: ms-yourphone://"
    Start-Process "ms-yourphone://"
    $launched = $true
}

# Step 4: Wait up to 30s for process to appear
Log "Waiting for PhoneExperienceHost..."
$t = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $t) {
    Start-Sleep -Seconds 2
    $proc = Get-Process -Name "PhoneExperienceHost" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($proc) {
        Log "  Process running PID $($proc.Id)"
        Write-Output "OK"
        exit 0
    }
}

Log "Timeout - Phone Link did not start"
Write-Output "FAIL"
exit 1

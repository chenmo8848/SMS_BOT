# check_status.ps1
# Outputs to stdout: ONLINE / OFFLINE / FROZEN

# Step 1: Process not found -> OFFLINE
$proc = Get-Process -Name "PhoneExperienceHost" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc) {
    Write-Output "OFFLINE"
    exit 0
}

# Step 2: Process not responding -> FROZEN
if ($proc.Responding -eq $false) {
    Write-Output "FROZEN"
    exit 0
}

# Step 3: Process running and responding -> ONLINE
# Registry and db checks are unreliable on this system
Write-Output "ONLINE"
exit 0

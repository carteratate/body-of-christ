# Keeps the Lenovo awake on AC power and starts WSL at sign-in.
# Run from an administrator PowerShell; see docs/setup/home-server/README.md, step f.
param([Parameter(Mandatory = $true)][string]$Distro)
$ErrorActionPreference = 'Stop'

# Never sleep or hibernate on AC power; closing the lid does nothing.
function Invoke-Powercfg([string[]]$Arguments) {
  & powercfg @Arguments
  if ($LASTEXITCODE -ne 0) { throw "powercfg $Arguments failed with exit code $LASTEXITCODE" }
}
Invoke-Powercfg '/change', 'standby-timeout-ac', '0'
Invoke-Powercfg '/change', 'hibernate-timeout-ac', '0'
Invoke-Powercfg '/setacvalueindex', 'SCHEME_CURRENT', 'SUB_BUTTONS', 'LIDACTION', '0'
Invoke-Powercfg '/setactive', 'SCHEME_CURRENT'
Write-Host "Power: no sleep or hibernate on AC; lid close does nothing (on AC)."

# At sign-in, start WSL and hold it open so systemd and the agent services keep running.
$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
  -Argument "-WindowStyle Hidden -NoProfile -Command wsl.exe -d '$Distro' --exec sleep infinity"
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
  -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 `
  -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName 'Keep WSL running' -Action $action -Trigger $trigger `
  -Settings $settings -Force | Out-Null
Write-Host "Task 'Keep WSL running' registered for $env:USERNAME (distro $Distro)."
Start-ScheduledTask -TaskName 'Keep WSL running'
Write-Host "Started it now as well."

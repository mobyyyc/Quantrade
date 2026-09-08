[CmdletBinding(SupportsShouldProcess)]
param(
    [ValidatePattern('^([01]\d|2[0-3]):[0-5]\d$')]
    [string]$BackupAt = "21:45",
    [ValidatePattern('^([01]\d|2[0-3]):[0-5]\d$')]
    [string]$DailyUpdateAt = "22:15"
)

$ErrorActionPreference = "Stop"
$isAdministrator = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)
if (-not $isAdministrator) {
    throw "Open PowerShell as Administrator, return to the Quantrade repository, and run .\scripts\install-operations-schedule.ps1."
}

$backupInstaller = Join-Path $PSScriptRoot "install-postgresql-backup-task.ps1"
$dailyInstaller = Join-Path $PSScriptRoot "install-daily-update-task.ps1"
$backupVerifier = Join-Path $PSScriptRoot "verify-postgresql-backup-task.ps1"
$dailyVerifier = Join-Path $PSScriptRoot "verify-daily-update-task.ps1"

if (-not $PSCmdlet.ShouldProcess("Quantrade scheduled operations", "Install and verify the approved schedule")) { return }

& $backupInstaller -At $BackupAt -Confirm:$false
& $dailyInstaller -At $DailyUpdateAt -Confirm:$false
$backup = & $backupVerifier -At $BackupAt
$daily = & $dailyVerifier -At $DailyUpdateAt

[pscustomobject]@{
    Contract = "quantrade_operations_schedule_v1"
    BackupSchedule = "Daily $BackupAt Eastern Standard Time"
    DailyUpdateSchedule = "Monday-Friday $DailyUpdateAt Eastern Standard Time"
    BackupVerified = $null -ne $backup
    DailyUpdateVerified = $null -ne $daily
    HiddenLaunchers = $true
    CodexRequired = $false
    WebAppRequired = $false
}

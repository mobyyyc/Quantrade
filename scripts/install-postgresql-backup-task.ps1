[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$TaskName = "Quantrade PostgreSQL Backup",
    [ValidatePattern('^([01]\d|2[0-3]):[0-5]\d$')][string]$At = "01:30",
    [string]$BackupDirectory = "data\backups\postgresql",
    [ValidateRange(1, 3650)][int]$RetentionDays = 30,
    [ValidateRange(1, 500)][int]$MinimumBackups = 7
)

$ErrorActionPreference = "Stop"
$isAdministrator = ([System.Security.Principal.WindowsPrincipal] [System.Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [System.Security.Principal.WindowsBuiltInRole]::Administrator
)
if (-not $isAdministrator) {
    throw "Task registration requires one elevated PowerShell run. Open PowerShell as Administrator and run .\scripts\install-postgresql-backup-task.ps1."
}
$expectedTimeZone = "Eastern Standard Time"
if ((Get-TimeZone).Id -ne $expectedTimeZone) { throw "Quantrade scheduling requires Windows time zone '$expectedTimeZone'." }
$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backupScript = (Resolve-Path (Join-Path $workspaceRoot "scripts\backup-postgresql.ps1")).Path
$envFile = (Resolve-Path (Join-Path $workspaceRoot ".env")).Path
$resolvedBackupDirectory = if ([System.IO.Path]::IsPathRooted($BackupDirectory)) {
    [System.IO.Path]::GetFullPath($BackupDirectory)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $workspaceRoot $BackupDirectory))
}
$powershellExecutable = (Get-Command powershell.exe -ErrorAction Stop).Source
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$triggerTime = [datetime]::Today.Add([TimeSpan]::ParseExact($At, 'hh\:mm', [Globalization.CultureInfo]::InvariantCulture))
$actionArguments = @(
    "-NoLogo", "-NoProfile", "-NonInteractive", "-WindowStyle Hidden", "-ExecutionPolicy Bypass",
    "-File `"$backupScript`"", "-EnvFile `"$envFile`"", "-BackupDirectory `"$resolvedBackupDirectory`"",
    "-RetentionDays $RetentionDays", "-MinimumBackups $MinimumBackups"
) -join " "
$action = New-ScheduledTaskAction -Execute $powershellExecutable -Argument $actionArguments -WorkingDirectory $workspaceRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $triggerTime
$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -StartWhenAvailable -Hidden -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$description = "Silently creates and verifies an atomic Quantrade PostgreSQL backup when the computer is available, then applies $RetentionDays-day retention while preserving at least $MinimumBackups archives. It does not wake the computer. Codex and the web app are not required."

if (-not $PSCmdlet.ShouldProcess($TaskName, "Register or replace Windows scheduled backup task")) { return }
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal `
    -Settings $settings -Description $description -Force | Out-Null

[pscustomobject]@{
    Contract = "windows_postgresql_backup_task_v2"
    TaskName = $TaskName
    Schedule = "Daily $At $expectedTimeZone"
    BackupDirectory = $resolvedBackupDirectory
    RetentionDays = $RetentionDays
    MinimumBackups = $MinimumBackups
    CodexRequired = $false
    WebAppRequired = $false
}

[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$TaskName = "Quantrade Daily Update",
    [ValidatePattern('^([01]\d|2[0-3]):[0-5]\d$')]
    [string]$At = "22:15"
)

$ErrorActionPreference = "Stop"
$isAdministrator = ([System.Security.Principal.WindowsPrincipal] [System.Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [System.Security.Principal.WindowsBuiltInRole]::Administrator
)
if (-not $isAdministrator) {
    throw "Task registration requires one elevated PowerShell run. Open PowerShell as Administrator, change to '$((Resolve-Path (Join-Path $PSScriptRoot "..")).Path)', and run .\scripts\install-daily-update-task.ps1."
}
$expectedTimeZone = "Eastern Standard Time"
$actualTimeZone = (Get-TimeZone).Id
if ($actualTimeZone -ne $expectedTimeZone) {
    throw "Quantrade scheduling requires Windows time zone '$expectedTimeZone'; found '$actualTimeZone'."
}

$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$dailyUpdateScript = (Resolve-Path (Join-Path $workspaceRoot "scripts\run-daily-update.ps1")).Path
$envFile = (Resolve-Path (Join-Path $workspaceRoot ".env")).Path
$powershellExecutable = (Get-Command powershell.exe -ErrorAction Stop).Source
$pythonLauncher = (Get-Command py.exe -ErrorAction Stop).Source
$currentIdentity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$currentUser = $currentIdentity.Name
$currentUserSid = $currentIdentity.User.Value
$triggerTime = [datetime]::Today.Add(
    [TimeSpan]::ParseExact($At, 'hh\:mm', [System.Globalization.CultureInfo]::InvariantCulture)
)

$actionArguments = @(
    "-NoLogo",
    "-NoProfile",
    "-NonInteractive",
    "-WindowStyle Hidden",
    "-ExecutionPolicy Bypass",
    "-File `"$dailyUpdateScript`"",
    "-EnvFile `"$envFile`""
) -join " "

$action = New-ScheduledTaskAction `
    -Execute $powershellExecutable `
    -Argument $actionArguments `
    -WorkingDirectory $workspaceRoot `
    -ErrorAction Stop
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -WeeksInterval 1 `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
    -At $triggerTime `
    -ErrorAction Stop
$principal = New-ScheduledTaskPrincipal `
    -UserId $currentUser `
    -LogonType Interactive `
    -RunLevel Limited `
    -ErrorAction Stop
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 10) `
    -StartWhenAvailable `
    -Hidden `
    -RunOnlyIfNetworkAvailable `
    -WakeToRun `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ErrorAction Stop
$description = "Runs Quantrade's canonical post-close daily update. Requires this Windows user, PostgreSQL, internet access, and configured .env credentials; Codex and the web app are not required."

if (-not $PSCmdlet.ShouldProcess($TaskName, "Register or replace Windows scheduled task")) {
    return
}
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description $description `
    -Force `
    -ErrorAction Stop | Out-Null

$registered = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$registeredAction = @($registered.Actions)[0]
$registeredTrigger = @($registered.Triggers)[0]
$expectedScriptArgument = "-File `"$dailyUpdateScript`""
$registeredUserSid = ([System.Security.Principal.NTAccount] $registered.Principal.UserId).Translate(
    [System.Security.Principal.SecurityIdentifier]
).Value
if (
    $registeredAction.Execute -ne $powershellExecutable `
    -or -not $registeredAction.Arguments.Contains($expectedScriptArgument) `
    -or $registeredAction.WorkingDirectory -ne $workspaceRoot `
    -or $registeredUserSid -ne $currentUserSid
) {
    throw "The registered task does not match the canonical Quantrade launch contract."
}

[pscustomobject]@{
    TaskName = $registered.TaskName
    State = $registered.State
    User = $registered.Principal.UserId
    LogonType = $registered.Principal.LogonType
    Schedule = "Monday-Friday $At $actualTimeZone"
    NextRunTime = (Get-ScheduledTaskInfo -TaskName $TaskName).NextRunTime
    CanonicalScript = $dailyUpdateScript
    EnvironmentFile = $envFile
    PowerShell = $powershellExecutable
    PythonLauncher = $pythonLauncher
    Contract = "windows_daily_update_task_v2"
    CodexRequired = $false
    WebAppRequired = $false
}

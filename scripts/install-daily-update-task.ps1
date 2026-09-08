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
$scheduledUpdateScript = (Resolve-Path (Join-Path $workspaceRoot "scripts\run-daily-update-scheduled.ps1")).Path
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
    "-File `"$scheduledUpdateScript`"",
    "-EnvFile `"$envFile`"",
    "-At $At"
) -join " "

$action = New-ScheduledTaskAction `
    -Execute $powershellExecutable `
    -Argument $actionArguments `
    -WorkingDirectory $workspaceRoot `
    -ErrorAction Stop
$weeklyTrigger = New-ScheduledTaskTrigger `
    -Weekly `
    -WeeksInterval 1 `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
    -At $triggerTime `
    -ErrorAction Stop
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser -ErrorAction Stop
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
$description = "Silently runs Quantrade's canonical post-close daily update at $At on weekdays. A logon trigger catches the same evening window only; it never backdates a prior-day score. Codex and the web app are not required."

if (-not $PSCmdlet.ShouldProcess($TaskName, "Register or replace Windows scheduled task")) {
    return
}
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger @($weeklyTrigger, $logonTrigger) `
    -Principal $principal `
    -Settings $settings `
    -Description $description `
    -Force `
    -ErrorAction Stop | Out-Null

$registered = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$registeredAction = @($registered.Actions)[0]
$registeredTriggers = @($registered.Triggers)
$expectedScriptArgument = "-File `"$scheduledUpdateScript`""
$registeredUserSid = ([System.Security.Principal.NTAccount] $registered.Principal.UserId).Translate(
    [System.Security.Principal.SecurityIdentifier]
).Value
if (
    $registeredAction.Execute -ne $powershellExecutable `
    -or -not $registeredAction.Arguments.Contains($expectedScriptArgument) `
    -or -not $registeredAction.Arguments.Contains("-At $At") `
    -or $registeredAction.WorkingDirectory -ne $workspaceRoot `
    -or $registeredUserSid -ne $currentUserSid `
    -or $registeredTriggers.Count -ne 2
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
    ScheduledWrapper = $scheduledUpdateScript
    CanonicalScript = (Resolve-Path (Join-Path $workspaceRoot "scripts\run-daily-update.ps1")).Path
    EnvironmentFile = $envFile
    PowerShell = $powershellExecutable
    PythonLauncher = $pythonLauncher
    Contract = "windows_daily_update_task_v3"
    CodexRequired = $false
    WebAppRequired = $false
}

[CmdletBinding()]
param(
    [string]$TaskName = "Quantrade Daily Update",
    [string]$At = "22:15",
    [string]$RetryAt = "23:00"
)

$ErrorActionPreference = "Stop"
$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$scheduledUpdateScript = (Resolve-Path (Join-Path $workspaceRoot "scripts\run-daily-update-scheduled.ps1")).Path
$canonicalScript = (Resolve-Path (Join-Path $workspaceRoot "scripts\run-daily-update.ps1")).Path
$envFile = (Resolve-Path (Join-Path $workspaceRoot ".env")).Path
$powershellExecutable = (Get-Command powershell.exe -ErrorAction Stop).Source
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$taskInfo = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop
$action = @($task.Actions)[0]
$triggers = @($task.Triggers)
$weeklyTrigger = @($triggers | Where-Object { $_.CimClass.CimClassName -eq "MSFT_TaskWeeklyTrigger" })
$logonTrigger = @($triggers | Where-Object { $_.CimClass.CimClassName -eq "MSFT_TaskLogonTrigger" })
$primaryTrigger = @($weeklyTrigger | Where-Object { $_.StartBoundary.Contains("T$At") })
$retryTrigger = @($weeklyTrigger | Where-Object { $_.StartBoundary.Contains("T$RetryAt") })
$expectedArguments = @(
    "-WindowStyle Hidden",
    "-File `"$scheduledUpdateScript`"",
    "-EnvFile `"$envFile`"",
    "-At $At"
)
$violations = [System.Collections.Generic.List[string]]::new()

if ($action.Execute -ne $powershellExecutable) { $violations.Add("unexpected PowerShell executable") }
foreach ($argument in $expectedArguments) {
    if (-not $action.Arguments.Contains($argument)) { $violations.Add("missing action argument: $argument") }
}
if ($action.WorkingDirectory -ne $workspaceRoot) { $violations.Add("unexpected working directory") }
if ($task.Principal.LogonType -ne "Interactive") { $violations.Add("task is not current-user interactive") }
if ($task.Principal.RunLevel -ne "Limited") { $violations.Add("task does not use limited privileges") }
if ($task.Settings.MultipleInstances -ne "IgnoreNew") { $violations.Add("overlapping runs are not ignored") }
if (-not $task.Settings.RunOnlyIfNetworkAvailable) { $violations.Add("network availability is not required") }
if (-not $task.Settings.StartWhenAvailable) { $violations.Add("missed-run recovery is disabled") }
if (-not $task.Settings.WakeToRun) { $violations.Add("wake-to-run is disabled") }
if (-not $task.Settings.Hidden) { $violations.Add("task is not hidden") }
if ($triggers.Count -ne 3 -or $weeklyTrigger.Count -ne 2 -or $logonTrigger.Count -ne 1) { $violations.Add("expected two weekly and one logon trigger") }
if ($primaryTrigger.Count -ne 1 -or -not $primaryTrigger[0].Enabled) { $violations.Add("unexpected primary weekly trigger") }
if ($retryTrigger.Count -ne 1 -or -not $retryTrigger[0].Enabled) { $violations.Add("unexpected retry weekly trigger") }
if ($logonTrigger.Count -eq 1 -and -not $logonTrigger[0].Enabled) { $violations.Add("logon catch-up trigger is disabled") }
$wrapper = Get-Content -LiteralPath $scheduledUpdateScript -Raw
if (-not $wrapper.Contains($canonicalScript.Split('\')[-1]) -or -not $wrapper.Contains('$isDue')) { $violations.Add("scheduled wrapper does not guard and invoke the canonical update") }

if ($violations.Count) {
    throw "Scheduled task verification failed: $($violations -join '; ')"
}

[pscustomobject]@{
    Contract = "windows_daily_update_task_v4"
    TaskName = $task.TaskName
    State = $task.State
    User = $task.Principal.UserId
    LogonType = $task.Principal.LogonType
    RunLevel = $task.Principal.RunLevel
    Execute = $action.Execute
    Arguments = $action.Arguments
    WorkingDirectory = $action.WorkingDirectory
    StartBoundary = if ($primaryTrigger.Count -eq 1) { $primaryTrigger[0].StartBoundary } else { $null }
    RetryStartBoundary = if ($retryTrigger.Count -eq 1) { $retryTrigger[0].StartBoundary } else { $null }
    DaysOfWeek = if ($primaryTrigger.Count -eq 1) { $primaryTrigger[0].DaysOfWeek } else { $null }
    LogonCatchUp = $logonTrigger.Count -eq 1
    NextRunTime = $taskInfo.NextRunTime
    LastTaskResult = $taskInfo.LastTaskResult
    MultipleInstances = $task.Settings.MultipleInstances
    RunOnlyIfNetworkAvailable = $task.Settings.RunOnlyIfNetworkAvailable
    StartWhenAvailable = $task.Settings.StartWhenAvailable
    WakeToRun = $task.Settings.WakeToRun
    Hidden = $task.Settings.Hidden
    CodexRequired = $false
    WebAppRequired = $false
}

[CmdletBinding()]
param(
    [string]$TaskName = "Quantrade Daily Update",
    [string]$At = "22:15"
)

$ErrorActionPreference = "Stop"
$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$dailyUpdateScript = (Resolve-Path (Join-Path $workspaceRoot "scripts\run-daily-update.ps1")).Path
$envFile = (Resolve-Path (Join-Path $workspaceRoot ".env")).Path
$powershellExecutable = (Get-Command powershell.exe -ErrorAction Stop).Source
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$taskInfo = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop
$action = @($task.Actions)[0]
$trigger = @($task.Triggers)[0]
$expectedArguments = @(
    "-File `"$dailyUpdateScript`"",
    "-EnvFile `"$envFile`""
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
if (-not $trigger.Enabled) { $violations.Add("trigger is disabled") }
if (-not $trigger.StartBoundary.Contains("T$At")) { $violations.Add("unexpected trigger time") }

if ($violations.Count) {
    throw "Scheduled task verification failed: $($violations -join '; ')"
}

[pscustomobject]@{
    Contract = "windows_daily_update_task_v1"
    TaskName = $task.TaskName
    State = $task.State
    User = $task.Principal.UserId
    LogonType = $task.Principal.LogonType
    RunLevel = $task.Principal.RunLevel
    Execute = $action.Execute
    Arguments = $action.Arguments
    WorkingDirectory = $action.WorkingDirectory
    StartBoundary = $trigger.StartBoundary
    DaysOfWeek = $trigger.DaysOfWeek
    NextRunTime = $taskInfo.NextRunTime
    LastTaskResult = $taskInfo.LastTaskResult
    MultipleInstances = $task.Settings.MultipleInstances
    RunOnlyIfNetworkAvailable = $task.Settings.RunOnlyIfNetworkAvailable
    StartWhenAvailable = $task.Settings.StartWhenAvailable
    WakeToRun = $task.Settings.WakeToRun
    CodexRequired = $false
    WebAppRequired = $false
}

[CmdletBinding()]
param(
    [string]$TaskName = "Quantrade PostgreSQL Backup",
    [string]$At = "01:30"
)

$ErrorActionPreference = "Stop"
$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backupScript = (Resolve-Path (Join-Path $workspaceRoot "scripts\backup-postgresql.ps1")).Path
$envFile = (Resolve-Path (Join-Path $workspaceRoot ".env")).Path
$powershellExecutable = (Get-Command powershell.exe -ErrorAction Stop).Source
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$taskInfo = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop
$action = @($task.Actions)[0]
$trigger = @($task.Triggers)[0]
$violations = [Collections.Generic.List[string]]::new()
foreach ($expected in @("-File `"$backupScript`"", "-EnvFile `"$envFile`"", "-RetentionDays 30", "-MinimumBackups 7")) {
    if (-not $action.Arguments.Contains($expected)) { $violations.Add("missing action argument: $expected") }
}
if ($action.Execute -ne $powershellExecutable) { $violations.Add("unexpected PowerShell executable") }
if ($action.WorkingDirectory -ne $workspaceRoot) { $violations.Add("unexpected working directory") }
if ($task.Principal.LogonType -ne "Interactive" -or $task.Principal.RunLevel -ne "Limited") { $violations.Add("unexpected task principal") }
if ($task.Settings.MultipleInstances -ne "IgnoreNew") { $violations.Add("overlapping backups are not ignored") }
if (-not $task.Settings.StartWhenAvailable -or -not $task.Settings.WakeToRun) { $violations.Add("recovery or wake setting is disabled") }
if (-not $trigger.Enabled -or -not $trigger.StartBoundary.Contains("T$At")) { $violations.Add("unexpected backup trigger") }
if ($violations.Count) { throw "Scheduled backup verification failed: $($violations -join '; ')" }

[pscustomobject]@{
    Contract = "windows_postgresql_backup_task_v1"
    TaskName = $task.TaskName
    State = $task.State
    User = $task.Principal.UserId
    StartBoundary = $trigger.StartBoundary
    NextRunTime = $taskInfo.NextRunTime
    LastTaskResult = $taskInfo.LastTaskResult
    Execute = $action.Execute
    Arguments = $action.Arguments
    CodexRequired = $false
    WebAppRequired = $false
}

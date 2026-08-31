[CmdletBinding(SupportsShouldProcess, ConfirmImpact = "High")]
param([string]$TaskName = "Quantrade PostgreSQL Backup")

$ErrorActionPreference = "Stop"
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Output "Scheduled task '$TaskName' is not installed."
    exit 0
}
if ($PSCmdlet.ShouldProcess($TaskName, "Unregister Windows scheduled backup task")) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Output "Scheduled task '$TaskName' was removed. Existing backup archives were not deleted."
}

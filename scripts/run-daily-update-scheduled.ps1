[CmdletBinding()]
param(
    [string]$EnvFile = ".env",
    [ValidatePattern('^([01]\d|2[0-3]):[0-5]\d$')]
    [string]$At = "22:15",
    [string]$LogFile = "data\logs\daily-update-scheduler.log"
)

$ErrorActionPreference = "Stop"
$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$canonicalScript = (Resolve-Path (Join-Path $workspaceRoot "scripts\run-daily-update.ps1")).Path
$resolvedEnvFile = if ([System.IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $workspaceRoot $EnvFile }
$resolvedLogFile = if ([System.IO.Path]::IsPathRooted($LogFile)) { $LogFile } else { Join-Path $workspaceRoot $LogFile }
$logDirectory = Split-Path -Parent $resolvedLogFile
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null

$now = Get-Date
$scheduledTime = [TimeSpan]::ParseExact($At, 'hh\:mm', [Globalization.CultureInfo]::InvariantCulture)
$isWeekday = $now.DayOfWeek -notin @([DayOfWeek]::Saturday, [DayOfWeek]::Sunday)
$isDue = $isWeekday -and $now.TimeOfDay -ge $scheduledTime
$stamp = $now.ToString("o")

if (-not $isDue) {
    Add-Content -LiteralPath $resolvedLogFile -Value "$stamp skipped: outside the weekday post-$At window"
    exit 0
}

Add-Content -LiteralPath $resolvedLogFile -Value "$stamp started: canonical daily update"
try {
    & $canonicalScript -EnvFile $resolvedEnvFile *>&1 | Tee-Object -FilePath $resolvedLogFile -Append
    $exitCode = $LASTEXITCODE
} catch {
    Add-Content -LiteralPath $resolvedLogFile -Value "$(Get-Date -Format o) failed: $($_.Exception.Message)"
    exit 1
}

Add-Content -LiteralPath $resolvedLogFile -Value "$(Get-Date -Format o) finished: exitCode=$exitCode"
exit $exitCode

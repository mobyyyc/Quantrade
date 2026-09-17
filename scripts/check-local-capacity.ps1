[CmdletBinding()]
param(
    [string]$EnvFile = ".env",
    [ValidateRange(1, 3650)][int]$BackupRetentionDays = 30,
    [ValidateRange(1, 500)][int]$MinimumBackups = 7,
    [switch]$FailOnWarning
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$workspaceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$resolvedEnvFile = if ([System.IO.Path]::IsPathRooted($EnvFile)) {
    $EnvFile
} else {
    Join-Path $workspaceRoot $EnvFile
}
if (-not (Test-Path -LiteralPath $resolvedEnvFile -PathType Leaf)) {
    throw "Missing local configuration: $resolvedEnvFile"
}

$arguments = @(
    '-3.14', '-m', 'quantrade_research.local_capacity',
    '--env-file', $resolvedEnvFile,
    '--workspace', $workspaceRoot,
    '--backup-retention-days', $BackupRetentionDays,
    '--minimum-backups', $MinimumBackups
)
if ($FailOnWarning) { $arguments += '--fail-on-warning' }
$previousPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = Join-Path $workspaceRoot 'services/research/src'
try {
    & py @arguments
    if ($LASTEXITCODE -ne 0) { throw "Local capacity check failed with exit code $LASTEXITCODE." }
} finally {
    $env:PYTHONPATH = $previousPythonPath
}

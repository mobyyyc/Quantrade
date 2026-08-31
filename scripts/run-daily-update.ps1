[CmdletBinding()]
param(
    [string]$EnvFile = ".env",
    [switch]$Describe
)

$ErrorActionPreference = "Stop"
$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$resolvedEnvFile = if ([System.IO.Path]::IsPathRooted($EnvFile)) {
    $EnvFile
} else {
    Join-Path $workspaceRoot $EnvFile
}

if (-not (Test-Path -LiteralPath $resolvedEnvFile -PathType Leaf)) {
    throw "Environment file not found: $resolvedEnvFile"
}

# This script is the only supported executable boundary for routine daily updates.
# The web route, interactive terminal, and scheduler all invoke it.
$previousPythonPath = $env:PYTHONPATH
$sourcePath = Join-Path $workspaceRoot "services\research\src"
$pythonArguments = @(
    "-3.14",
    "-m",
    "quantrade_research.manual_daily_update",
    "--env-file",
    $resolvedEnvFile
)

if ($Describe) {
    [pscustomobject]@{
        contract = "canonical_daily_update_v1"
        workspaceRoot = $workspaceRoot
        envFile = $resolvedEnvFile
        workingDirectory = $workspaceRoot
        pythonPath = $sourcePath
        executable = "py"
        arguments = $pythonArguments
    } | ConvertTo-Json -Compress
    exit 0
}

$env:PYTHONPATH = $sourcePath

Push-Location $workspaceRoot
try {
    & py @pythonArguments
    $exitCode = $LASTEXITCODE
} finally {
    Pop-Location
    $env:PYTHONPATH = $previousPythonPath
}

if ($exitCode -ne 0) {
    exit $exitCode
}

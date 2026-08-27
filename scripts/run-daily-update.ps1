[CmdletBinding()]
param(
    [string]$EnvFile = ".env"
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

# Match the local web route: same interpreter, module, source path, and .env file.
$previousPythonPath = $env:PYTHONPATH
$sourcePath = Join-Path $workspaceRoot "services\research\src"
$env:PYTHONPATH = if ($previousPythonPath) { "$sourcePath;$previousPythonPath" } else { $sourcePath }

Push-Location $workspaceRoot
try {
    & py -3.14 -m quantrade_research.manual_daily_update --env-file $resolvedEnvFile
    $exitCode = $LASTEXITCODE
} finally {
    Pop-Location
    $env:PYTHONPATH = $previousPythonPath
}

if ($exitCode -ne 0) {
    exit $exitCode
}

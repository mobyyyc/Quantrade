[CmdletBinding()]
param(
    [string]$EnvFile = ".env.demo"
)

$ErrorActionPreference = "Stop"
$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$resolvedEnvFile = if ([System.IO.Path]::IsPathRooted($EnvFile)) {
    $EnvFile
} else {
    Join-Path $workspaceRoot $EnvFile
}
if (-not (Test-Path -LiteralPath $resolvedEnvFile -PathType Leaf)) {
    throw "Demo environment file not found: $resolvedEnvFile. Copy .env.demo.example to .env.demo first."
}

$previousPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = Join-Path $workspaceRoot "services\research\src"
Push-Location $workspaceRoot
try {
    Write-Host "Resetting the fixed local quantrade_demo database..."
    & py -3.14 -m quantrade_research.demo_database --env-file $resolvedEnvFile
    if ($LASTEXITCODE -ne 0) { throw "Synthetic demo database setup failed." }
} finally {
    Pop-Location
    $env:PYTHONPATH = $previousPythonPath
}

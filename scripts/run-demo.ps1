[CmdletBinding()]
param(
    [string]$EnvFile = ".env.demo",
    [switch]$SkipSetup
)

$ErrorActionPreference = "Stop"
$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$resolvedEnvFile = if ([System.IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $workspaceRoot $EnvFile }
if (-not (Test-Path -LiteralPath $resolvedEnvFile -PathType Leaf)) {
    throw "Demo environment file not found: $resolvedEnvFile. Copy .env.demo.example to .env.demo first."
}
if (-not $SkipSetup) {
    & (Join-Path $PSScriptRoot "setup-demo.ps1") -EnvFile $resolvedEnvFile
    if ($LASTEXITCODE -ne 0) { throw "Synthetic demo setup failed." }
}

. (Join-Path $PSScriptRoot "postgres-backup-common.ps1")
$databaseConfig = Get-QuantradeDatabaseConfig -EnvFile $resolvedEnvFile
if ($databaseConfig.Host -notin @("localhost", "127.0.0.1", "::1")) {
    throw "The synthetic demo is restricted to a local PostgreSQL server."
}
$encodedUser = [System.Uri]::EscapeDataString($databaseConfig.User)
$encodedPassword = [System.Uri]::EscapeDataString($databaseConfig.Password)
$uriHost = if ($databaseConfig.Host -eq "::1") { "[::1]" } else { $databaseConfig.Host }
$demoDatabaseUrl = "postgresql://${encodedUser}:${encodedPassword}@${uriHost}:$($databaseConfig.Port)/quantrade_demo"

$previousDatabaseUrl = $env:DATABASE_URL
$previousDemoMode = $env:QUANTRADE_DEMO_MODE
$previousWorkspaceRoot = $env:QUANTRADE_WORKSPACE_ROOT
$pushedLocation = $false
$exitCode = 0
try {
    $env:DATABASE_URL = $demoDatabaseUrl
    $env:QUANTRADE_DEMO_MODE = "1"
    $env:QUANTRADE_WORKSPACE_ROOT = $workspaceRoot
    Push-Location $workspaceRoot
    $pushedLocation = $true
    Write-Host "Starting Quantrade with deterministic synthetic data at http://localhost:3000 ..."
    & corepack pnpm dev:web
    $exitCode = $LASTEXITCODE
} finally {
    if ($pushedLocation) { Pop-Location }
    $env:DATABASE_URL = $previousDatabaseUrl
    $env:QUANTRADE_DEMO_MODE = $previousDemoMode
    $env:QUANTRADE_WORKSPACE_ROOT = $previousWorkspaceRoot
}
if ($exitCode -ne 0) { exit $exitCode }

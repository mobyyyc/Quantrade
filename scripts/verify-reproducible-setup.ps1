[CmdletBinding()]
param(
    [string]$EnvFile = ".env.demo"
)

$ErrorActionPreference = "Stop"
$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$resolvedEnvFile = if ([System.IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $workspaceRoot $EnvFile }
if (-not (Test-Path -LiteralPath $resolvedEnvFile -PathType Leaf)) { throw "Demo environment file not found: $resolvedEnvFile" }
$databaseLine = Get-Content -LiteralPath $resolvedEnvFile | Where-Object { $_ -match '^\s*DATABASE_URL=' } | Select-Object -First 1
if (-not $databaseLine) { throw "DATABASE_URL is missing from $resolvedEnvFile." }
$demoDatabaseUrl = ($databaseLine -replace '^\s*DATABASE_URL=', '').Trim().Trim('"').Trim("'")

$previousPythonPath = $env:PYTHONPATH
$previousE2eUrl = $env:QUANTRADE_E2E_ADMIN_DATABASE_URL
try {
    Push-Location $workspaceRoot
    & (Join-Path $PSScriptRoot "setup-demo.ps1") -EnvFile $resolvedEnvFile
    if ($LASTEXITCODE -ne 0) { throw "Synthetic database verification failed." }

    Write-Host "Resolving the canonical daily-update plan without network calls or writes..."
    & (Join-Path $PSScriptRoot "run-daily-update.ps1") -EnvFile $resolvedEnvFile -DryRun -ScoreDate "2026-08-28"
    if ($LASTEXITCODE -ne 0) { throw "Daily-update dry run failed." }

    Write-Host "Running research tests..."
    $env:PYTHONPATH = Join-Path $workspaceRoot "services\research\src"
    & py -3.14 -m unittest discover -s services/research/tests
    if ($LASTEXITCODE -ne 0) { throw "Research tests failed." }

    Write-Host "Linting and building the web application..."
    & corepack pnpm lint:web
    if ($LASTEXITCODE -ne 0) { throw "Web lint failed." }
    & corepack pnpm build:web
    if ($LASTEXITCODE -ne 0) { throw "Web build failed." }

    Write-Host "Running the isolated browser suite against deterministic fixtures..."
    $env:QUANTRADE_E2E_ADMIN_DATABASE_URL = $demoDatabaseUrl
    & corepack pnpm --filter @quantrade/web test:e2e
    if ($LASTEXITCODE -ne 0) { throw "Browser verification failed." }
    Write-Host "Independent reproduction verification passed."
} finally {
    Pop-Location
    $env:PYTHONPATH = $previousPythonPath
    $env:QUANTRADE_E2E_ADMIN_DATABASE_URL = $previousE2eUrl
}

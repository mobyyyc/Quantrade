[CmdletBinding()]
param(
    [ValidatePattern('^\d{4}-\d{2}-\d{2}$')]
    [string]$Start = '2021-01-01',

    [ValidatePattern('^\d{4}-\d{2}-\d{2}$')]
    [string]$End = '2026-06-30',

    [ValidateRange(1, 100)]
    [int]$BatchSize = 100,

    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$researchDirectory = Join-Path $repositoryRoot 'services/research'
$environmentFile = Join-Path $repositoryRoot '.env'

if (-not (Test-Path -LiteralPath $environmentFile -PathType Leaf)) {
    throw "Missing local configuration file: $environmentFile"
}

try {
    $codeRevision = (git -C $repositoryRoot rev-parse HEAD).Trim()
} catch {
    throw 'Could not resolve the current Git revision. Run this script from a cloned Quantrade repository.'
}

Push-Location $researchDirectory
try {
    Write-Host 'Registering the fixed Tier-B current-survivors cohort (safe to repeat)...' -ForegroundColor Cyan
    & py -3.14 -m quantrade_research.register_historical_cohort `
        --source-universe-code sp500 `
        --code-revision $codeRevision `
        --env-file $environmentFile
    if ($LASTEXITCODE -ne 0) { throw "Cohort registration failed with exit code $LASTEXITCODE." }

    $arguments = @(
        '-m', 'quantrade_research.historical_market_backfill',
        '--start', $Start,
        '--end', $End,
        '--batch-size', $BatchSize,
        '--env-file', $environmentFile
    )
    if ($DryRun) { $arguments += '--dry-run' }

    if ($DryRun) {
        Write-Host "Validating the historical backfill plan for $Start through $End..." -ForegroundColor Yellow
    } else {
        Write-Host "Starting/resuming historical market download for $Start through $End..." -ForegroundColor Cyan
        Write-Host 'Press Ctrl+C to stop safely; rerun this exact command later to resume incomplete chunks.' -ForegroundColor Yellow
    }

    & py -3.14 @arguments
    if ($LASTEXITCODE -ne 0) { throw "Historical backfill failed with exit code $LASTEXITCODE." }
} finally {
    Pop-Location
}

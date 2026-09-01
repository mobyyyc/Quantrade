[CmdletBinding()]
param(
    [ValidatePattern('^$|^\d{4}-\d{2}-\d{2}$')]
    [string]$Start = '',

    [ValidatePattern('^$|^\d{4}-\d{2}-\d{2}$')]
    [string]$End = '',

    [ValidateRange(1, 365)]
    [int]$LookbackDays = 45,

    [ValidateRange(1, 100)]
    [int]$BatchSize = 100,

    [switch]$FailOnFindings
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ([bool]$Start -ne [bool]$End) {
    throw 'Start and End must be supplied together.'
}

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$researchDirectory = Join-Path $repositoryRoot 'services/research'
$environmentFile = Join-Path $repositoryRoot '.env'
$reportDirectory = Join-Path $repositoryRoot 'data/derived/market-reconciliation'

if (-not (Test-Path -LiteralPath $environmentFile -PathType Leaf)) {
    throw "Missing local configuration file: $environmentFile"
}

$codeRevision = (git -C $repositoryRoot rev-parse HEAD).Trim()
$timestamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$output = Join-Path $reportDirectory "alpaca-reconciliation-$timestamp.json"
$arguments = @(
    '-m', 'quantrade_research.market_data_reconciliation',
    '--lookback-days', $LookbackDays,
    '--batch-size', $BatchSize,
    '--code-revision', $codeRevision,
    '--output', $output,
    '--env-file', $environmentFile
)
if ($Start) { $arguments += @('--start', $Start, '--end', $End) }
if ($FailOnFindings) { $arguments += '--fail-on-findings' }

New-Item -ItemType Directory -Path $reportDirectory -Force | Out-Null
Push-Location $researchDirectory
try {
    Write-Host 'Comparing fresh Alpaca responses with the normalized market-data ledger...' -ForegroundColor Cyan
    Write-Host 'This audit is read-only and will not repair or overwrite market data.' -ForegroundColor Yellow
    & py -3.14 @arguments
    if ($LASTEXITCODE -ne 0) { throw "Market reconciliation failed with exit code $LASTEXITCODE." }
} finally {
    Pop-Location
}

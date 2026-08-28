[CmdletBinding()]
param(
    [ValidateRange(100, 50000)]
    [int]$BatchSize = 5000,

    [ValidateRange(1, 1000)]
    [int]$ProgressEvery = 10,

    [int]$MaxBatches,

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

Push-Location $researchDirectory
try {
    $arguments = @('-m', 'quantrade_research.backfill_sec_fact_observations', '--batch-size', $BatchSize,
        '--progress-every', $ProgressEvery, '--env-file', $environmentFile)
    if ($PSBoundParameters.ContainsKey('MaxBatches')) { $arguments += @('--max-batches', $MaxBatches) }
    if ($DryRun) { $arguments += '--dry-run' }
    & py -3.14 @arguments
    if ($LASTEXITCODE -ne 0) { throw "Legacy SEC fact snapshot failed with exit code $LASTEXITCODE." }
} finally {
    Pop-Location
}

[CmdletBinding()]
param(
    [string]$AsOf = '',
    [string]$PeriodStart = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$environmentFile = Join-Path $repositoryRoot '.env'
if (-not (Test-Path -LiteralPath $environmentFile -PathType Leaf)) {
    throw "Missing local configuration: $environmentFile"
}
$codeRevision = git -C $repositoryRoot rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve the code revision.' }
$reportId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$output = Join-Path $repositoryRoot "data/derived/sec-coverage/$reportId"
$arguments = @('-3.14', '-m', 'quantrade_research.sec_coverage_report',
    '--env-file', $environmentFile, '--code-revision', $codeRevision.Trim(), '--output', $output)
if ($AsOf) { $arguments += @('--as-of', $AsOf) }
if ($PeriodStart) { $arguments += @('--period-start', $PeriodStart) }
$previousPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = Join-Path $repositoryRoot 'services/research/src'
Push-Location $repositoryRoot
try {
    Write-Host 'Inspecting stored SEC coverage only. No downloads or database changes.'
    & py @arguments
    if ($LASTEXITCODE -ne 0) { throw "SEC coverage report failed with exit code $LASTEXITCODE." }
} finally {
    Pop-Location
    $env:PYTHONPATH = $previousPythonPath
}

[CmdletBinding()]
param([switch]$Apply)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root '.env'
if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) { throw "Missing local configuration: $envFile" }
$reportRoot = Join-Path $root 'data/derived/retention-plans'
$id = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
$output = Join-Path $reportRoot ($id + '.json')
$arguments = @('-3.14','-m','quantrade_research.storage_retention','--env-file',$envFile,
    '--data-root',(Join-Path $root 'data'),'--output',$output)
if ($Apply) { $arguments += '--apply' }
$previous = $env:PYTHONPATH
$env:PYTHONPATH = Join-Path $root 'services/research/src'
try {
    & py @arguments
    if ($LASTEXITCODE -ne 0) { throw "Storage retention failed with exit code $LASTEXITCODE." }
} finally { $env:PYTHONPATH = $previous }

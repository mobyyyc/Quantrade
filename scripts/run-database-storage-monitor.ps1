[CmdletBinding()]
param([switch]$FailOnWarning)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root '.env'
if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) { throw "Missing local configuration: $envFile" }
$revision = git -C $root rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve the code revision.' }
$reportRoot = Join-Path $root 'data/derived/database-storage'
$id = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
$output = Join-Path $reportRoot $id
$arguments = @('-3.14','-m','quantrade_research.database_storage_monitor','--env-file',$envFile,
    '--report-root',$reportRoot,'--output',$output,'--code-revision',$revision.Trim())
if ($FailOnWarning) { $arguments += '--fail-on-warning' }
$previous = $env:PYTHONPATH
$env:PYTHONPATH = Join-Path $root 'services/research/src'
try {
    & py @arguments
    if ($LASTEXITCODE -ne 0) { throw "Database storage monitor failed with exit code $LASTEXITCODE." }
} finally { $env:PYTHONPATH = $previous }

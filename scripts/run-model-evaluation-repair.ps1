[CmdletBinding()]
param([string]$Output = '')
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repositoryRoot = Split-Path -Parent $PSScriptRoot
if (-not $Output) {
    $Output = 'data/derived/evaluation-repair/' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff')
}
Push-Location $repositoryRoot
try {
    & py -3.14 -m quantrade_research.model_evaluation_repair --output $Output
    if ($LASTEXITCODE -ne 0) { throw "Evaluation repair failed (exit $LASTEXITCODE). The run directory is retained; no live model was changed." }
} finally {
    Pop-Location
}

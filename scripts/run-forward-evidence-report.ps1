[CmdletBinding()]
param(
    [string]$EnvFile = ".env",
    [string]$PeriodStart = "",
    [string]$AsOfDate = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$resolvedEnvFile = if ([IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $repositoryRoot $EnvFile }
if (-not (Test-Path -LiteralPath $resolvedEnvFile -PathType Leaf)) {
    throw "Environment file not found: $resolvedEnvFile"
}
$codeRevision = (& git -C $repositoryRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw "Cannot resolve the code revision." }
$reportId = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssfffZ") + "-" + [guid]::NewGuid().ToString("N").Substring(0, 8)
$output = Join-Path $repositoryRoot "data/derived/forward-evidence/$reportId"
$arguments = @(
    "-3.14", "-m", "quantrade_research.forward_evidence_report",
    "--env-file", $resolvedEnvFile,
    "--code-revision", $codeRevision,
    "--output", $output
)
if ($PeriodStart) { $arguments += @("--period-start", $PeriodStart) }
if ($AsOfDate) { $arguments += @("--as-of-date", $AsOfDate) }
$previousPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = Join-Path $repositoryRoot "services/research/src"
Push-Location $repositoryRoot
try {
    Write-Host "Publishing read-only post-deployment evidence. No model will be trained or changed."
    & py @arguments
    if ($LASTEXITCODE -ne 0) { throw "Forward-evidence report failed with exit code $LASTEXITCODE." }
} finally {
    Pop-Location
    $env:PYTHONPATH = $previousPythonPath
}

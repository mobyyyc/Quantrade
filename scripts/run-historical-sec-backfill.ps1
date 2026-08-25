[CmdletBinding()]
param(
    [ValidateRange(0.10, 2.00)]
    [double]$MinimumRequestInterval = 0.12,

    [switch]$SingleCompanySmokeTest
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
    if ($SingleCompanySmokeTest) {
        $cikArgument = @('--cik', '0000320193')
        Write-Host 'Running the historical SEC smoke test for Apple (CIK 0000320193)...' -ForegroundColor Yellow
    } else {
        $databaseLine = Get-Content $environmentFile | Where-Object { $_ -match '^DATABASE_URL=' } | Select-Object -First 1
        if ($null -eq $databaseLine) { throw 'DATABASE_URL is required in .env.' }
        $databaseUrl = $databaseLine.Substring('DATABASE_URL='.Length)
        $ciks = & 'D:\PostgreSQL\18\bin\psql.exe' "$databaseUrl" -Atc "SELECT string_agg(identifier_value, ',' ORDER BY identifier_value) FROM quantrade.security_identifiers WHERE identifier_type='cik' AND security_id IN (SELECT membership.security_id FROM quantrade.research_cohort_memberships membership JOIN quantrade.research_cohorts cohort ON cohort.research_cohort_id=membership.research_cohort_id WHERE cohort.cohort_code='sp500_current_survivors_v1');"
        if ([string]::IsNullOrWhiteSpace($ciks)) { throw 'The Tier-B historical cohort is not registered. Run the historical market runner first.' }
        $cikArgument = @('--ciks', $ciks.Trim())
        Write-Host 'Starting historical SEC submission and XBRL backfill for 500 companies...' -ForegroundColor Cyan
        Write-Host 'Press Ctrl+C to stop. Re-running is safe because filings, facts, and raw artifacts are deduplicated.' -ForegroundColor Yellow
    }

    & py -3.14 -m quantrade_research.ingest_filings @cikArgument `
        --include-history `
        --code-revision $codeRevision `
        --minimum-request-interval $MinimumRequestInterval `
        --env-file $environmentFile
    if ($LASTEXITCODE -ne 0) { throw "Historical SEC backfill failed with exit code $LASTEXITCODE." }
} finally {
    Pop-Location
}

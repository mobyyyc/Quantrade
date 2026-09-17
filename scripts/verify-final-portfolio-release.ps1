[CmdletBinding()]
param(
    [string]$EnvFile = ".env",
    [switch]$SkipRestore
)

$ErrorActionPreference = "Stop"
$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$resolvedEnvFile = if ([IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $workspaceRoot $EnvFile }
if (-not (Test-Path -LiteralPath $resolvedEnvFile -PathType Leaf)) {
    throw "Private local environment file not found: $resolvedEnvFile"
}

. (Join-Path $PSScriptRoot "postgres-backup-common.ps1")
$database = Get-QuantradeDatabaseConfig -EnvFile $resolvedEnvFile
if ($database.Host -notin @("localhost", "127.0.0.1", "::1")) {
    throw "Final local release verification requires a loopback PostgreSQL server."
}

$encodedUser = [Uri]::EscapeDataString($database.User)
$encodedPassword = [Uri]::EscapeDataString($database.Password)
$uriHost = if ($database.Host -eq "::1") { "[::1]" } else { $database.Host }
$demoDatabaseUrl = "postgresql://${encodedUser}:${encodedPassword}@${uriHost}:$($database.Port)/quantrade_demo"
$temporaryDemoEnv = Join-Path ([IO.Path]::GetTempPath()) "quantrade-release-$([Guid]::NewGuid().ToString('N')).env"

function Invoke-ReleaseStep {
    param([string]$Name, [scriptblock]$Action)
    Write-Host "`n== $Name =="
    & $Action
    if ($LASTEXITCODE -ne 0) { throw "$Name failed with exit code $LASTEXITCODE." }
}

function Test-DocumentationLinks {
    $failures = [Collections.Generic.List[string]]::new()
    $markdownFiles = @(& git -C $workspaceRoot ls-files "*.md")
    if ($LASTEXITCODE -ne 0) { throw "Unable to enumerate tracked Markdown files." }
    foreach ($relativePath in $markdownFiles) {
        $fullPath = Join-Path $workspaceRoot $relativePath
        $text = Get-Content -LiteralPath $fullPath -Raw
        foreach ($match in [regex]::Matches($text, '\[[^\]]+\]\(([^)]+)\)')) {
            $destination = $match.Groups[1].Value.Trim().Trim('<', '>')
            if ($destination -match '^(?:https?://|mailto:|#|codex:)') { continue }
            $destination = $destination.Split('#')[0]
            if (-not $destination) { continue }
            $destination = [Uri]::UnescapeDataString($destination)
            $candidate = Join-Path (Split-Path $fullPath -Parent) $destination
            if (-not (Test-Path -LiteralPath $candidate)) {
                $failures.Add("$relativePath -> $destination")
            }
        }
    }
    if ($failures.Count -gt 0) {
        throw "Documentation link audit failed:`n$($failures -join "`n")"
    }
    Write-Host "documentation_links=passed; markdown_files=$($markdownFiles.Count)"
}

function Test-TrackedArtifactHygiene {
    $tracked = @(& git -C $workspaceRoot ls-files)
    if ($LASTEXITCODE -ne 0) { throw "Unable to enumerate tracked files." }
    $forbidden = @($tracked | Where-Object {
        $_ -match '^(?:data/(?:raw|derived|backups|logs|quarantine)/|node_modules/|\.next/|playwright-report/|test-results/)' -or
        $_ -match '(?:^|/)\.env(?:\.|$)' -and $_ -notmatch '\.example$' -or
        $_ -match '\.(?:dump|backup|sqlite|sqlite3|db|pem|key)$'
    })
    if ($forbidden.Count -gt 0) {
        throw "Tracked artifact hygiene failed:`n$($forbidden -join "`n")"
    }
    Write-Host "tracked_artifact_hygiene=passed; tracked_files=$($tracked.Count)"
}

try {
    [IO.File]::WriteAllLines(
        $temporaryDemoEnv,
        @(
            "QUANTRADE_ENVIRONMENT=test",
            "SCORE_ELIGIBILITY_CONTRACT=exact_zero_coefficients_v1",
            "DATABASE_URL=$demoDatabaseUrl"
        ),
        [Text.UTF8Encoding]::new($false)
    )

    Push-Location $workspaceRoot
    try {
        Invoke-ReleaseStep "Independent reproduction suite" {
            & (Join-Path $PSScriptRoot "verify-reproducible-setup.ps1") -EnvFile $temporaryDemoEnv
        }
        Invoke-ReleaseStep "Full-history secret audit" {
            & (Join-Path $PSScriptRoot "audit-secrets.ps1") -History
        }
        Invoke-ReleaseStep "Tracked artifact hygiene" { Test-TrackedArtifactHygiene }
        Invoke-ReleaseStep "Documentation link audit" { Test-DocumentationLinks }
        Invoke-ReleaseStep "Daily-update schedule verification" {
            & (Join-Path $PSScriptRoot "verify-daily-update-task.ps1")
        }
        Invoke-ReleaseStep "Backup schedule verification" {
            & (Join-Path $PSScriptRoot "verify-postgresql-backup-task.ps1")
        }
        Invoke-ReleaseStep "Latest backup verification" {
            & (Join-Path $PSScriptRoot "verify-postgresql-backup.ps1")
        }
        if (-not $SkipRestore) {
            Invoke-ReleaseStep "Isolated PostgreSQL restore drill" {
                & (Join-Path $PSScriptRoot "test-postgresql-restore.ps1") -EnvFile $resolvedEnvFile
            }
        }
        Invoke-ReleaseStep "Local capacity gate" {
            & (Join-Path $PSScriptRoot "check-local-capacity.ps1") -EnvFile $resolvedEnvFile -FailOnWarning
        }
    } finally {
        Pop-Location
    }
} finally {
    Remove-Item -LiteralPath $temporaryDemoEnv -Force -ErrorAction SilentlyContinue
}

Write-Host "`nfinal_portfolio_release_verification=passed; restore_skipped=$($SkipRestore.IsPresent.ToString().ToLowerInvariant())"

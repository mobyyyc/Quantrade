[CmdletBinding()]
param(
    [string]$BackupFile,
    [string]$EnvFile = ".env",
    [string]$BackupDirectory = "data\backups\postgresql",
    [string]$PostgresBin
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "postgres-backup-common.ps1")
$workspaceRoot = Get-QuantradeWorkspaceRoot -ScriptRoot $PSScriptRoot
$resolvedEnvFile = Resolve-QuantradePath -Path $EnvFile -BasePath $workspaceRoot -MustExist
$resolvedBackupDirectory = Resolve-QuantradePath -Path $BackupDirectory -BasePath $workspaceRoot
if ($BackupFile) {
    $resolvedBackupFile = Resolve-QuantradePath -Path $BackupFile -BasePath $workspaceRoot -MustExist
} else {
    $latest = Get-ChildItem -LiteralPath $resolvedBackupDirectory -Filter "*.dump" -File -ErrorAction Stop |
        Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
    if (-not $latest) { throw "No PostgreSQL backup archive exists in $resolvedBackupDirectory." }
    $resolvedBackupFile = $latest.FullName
}
$metadataFile = "$resolvedBackupFile.json"
if (-not (Test-Path -LiteralPath $metadataFile -PathType Leaf)) { throw "Backup metadata is missing: $metadataFile" }
$metadata = Get-Content -LiteralPath $metadataFile -Raw | ConvertFrom-Json
$actualHash = (Get-FileHash -LiteralPath $resolvedBackupFile -Algorithm SHA256).Hash.ToLowerInvariant()
if ($metadata.contract -ne "quantrade_postgresql_backup_v1" -or $actualHash -ne $metadata.sha256) {
    throw "Restore drill refused an unverified backup archive."
}

$database = Get-QuantradeDatabaseConfig -EnvFile $resolvedEnvFile
$createdb = Get-QuantradePostgresTool -Name "createdb" -PostgresBin $PostgresBin
$dropdb = Get-QuantradePostgresTool -Name "dropdb" -PostgresBin $PostgresBin
$pgRestore = Get-QuantradePostgresTool -Name "pg_restore" -PostgresBin $PostgresBin
$psql = Get-QuantradePostgresTool -Name "psql" -PostgresBin $PostgresBin
$testDatabase = "quantrade_restore_drill_$([DateTime]::UtcNow.ToString('yyyyMMddHHmmss'))_$([Guid]::NewGuid().ToString('N').Substring(0, 6))"
if (-not $testDatabase.StartsWith("quantrade_restore_drill_")) { throw "Unsafe restore-drill database name." }
$created = $false

try {
    $serverArguments = @("--host=$($database.Host)", "--port=$($database.Port)", "--username=$($database.User)")
    Invoke-QuantradePostgresTool -Executable $createdb -Arguments ($serverArguments + @($testDatabase)) -Password $database.Password
    $created = $true
    $restoreArguments = @(
        Get-QuantradeConnectionArguments -DatabaseConfig $database -Database $testDatabase
    ) + @("--exit-on-error", "--no-owner", "--no-privileges", $resolvedBackupFile)
    Invoke-QuantradePostgresTool -Executable $pgRestore -Arguments $restoreArguments -Password $database.Password
    $query = "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'quantrade';"
    $tableCountOutput = Invoke-QuantradePostgresTool -Executable $psql `
        -Arguments ((Get-QuantradeConnectionArguments -DatabaseConfig $database -Database $testDatabase) + @("--tuples-only", "--no-align", "--command=$query")) `
        -Password $database.Password -CaptureOutput
    $tableCount = [int]($tableCountOutput | Select-Object -Last 1).ToString().Trim()
    if ($tableCount -lt 1) { throw "Restore drill found no tables in the quantrade schema." }
    [pscustomobject]@{
        Contract = "quantrade_postgresql_restore_drill_v1"
        BackupFile = $resolvedBackupFile
        TemporaryDatabase = $testDatabase
        QuantradeTableCount = $tableCount
        ChecksumVerified = $true
        RestoredAt = [DateTime]::UtcNow.ToString("o")
        TemporaryDatabaseRemoved = $true
    } | ConvertTo-Json -Depth 3
} finally {
    if ($created) {
        if (-not $testDatabase.StartsWith("quantrade_restore_drill_")) { throw "Refusing to remove an unsafe database name." }
        Invoke-QuantradePostgresTool -Executable $dropdb `
            -Arguments (@("--host=$($database.Host)", "--port=$($database.Port)", "--username=$($database.User)", "--force", $testDatabase)) `
            -Password $database.Password
    }
}

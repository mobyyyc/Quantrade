[CmdletBinding()]
param(
    [string]$BackupFile,
    [string]$BackupDirectory = "data\backups\postgresql",
    [string]$PostgresBin
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "postgres-backup-common.ps1")
$workspaceRoot = Get-QuantradeWorkspaceRoot -ScriptRoot $PSScriptRoot
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
if ($metadata.contract -ne "quantrade_postgresql_backup_v1") { throw "Backup metadata contract is unsupported." }
$actualHash = (Get-FileHash -LiteralPath $resolvedBackupFile -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $metadata.sha256) { throw "Backup checksum does not match its metadata." }
$pgRestore = Get-QuantradePostgresTool -Name "pg_restore" -PostgresBin $PostgresBin
$entryCount = Test-QuantradeBackupArchive -BackupFile $resolvedBackupFile -PgRestore $pgRestore

[pscustomobject]@{
    Contract = "quantrade_postgresql_backup_verification_v1"
    BackupFile = $resolvedBackupFile
    MetadataFile = $metadataFile
    Sha256 = $actualHash
    RestoreEntries = $entryCount
    VerifiedAt = [DateTime]::UtcNow.ToString("o")
} | ConvertTo-Json -Depth 3

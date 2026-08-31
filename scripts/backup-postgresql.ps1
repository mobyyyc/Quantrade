[CmdletBinding()]
param(
    [string]$EnvFile = ".env",
    [string]$BackupDirectory = "data\backups\postgresql",
    [ValidateRange(1, 3650)][int]$RetentionDays = 30,
    [ValidateRange(1, 500)][int]$MinimumBackups = 7,
    [string]$PostgresBin
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "postgres-backup-common.ps1")

$workspaceRoot = Get-QuantradeWorkspaceRoot -ScriptRoot $PSScriptRoot
$resolvedEnvFile = Resolve-QuantradePath -Path $EnvFile -BasePath $workspaceRoot -MustExist
$resolvedBackupDirectory = Resolve-QuantradePath -Path $BackupDirectory -BasePath $workspaceRoot
New-Item -ItemType Directory -Path $resolvedBackupDirectory -Force | Out-Null
$database = Get-QuantradeDatabaseConfig -EnvFile $resolvedEnvFile
$pgDump = Get-QuantradePostgresTool -Name "pg_dump" -PostgresBin $PostgresBin
$pgRestore = Get-QuantradePostgresTool -Name "pg_restore" -PostgresBin $PostgresBin
$lockPath = Join-Path $resolvedBackupDirectory ".backup.lock"
$lock = $null
$partialPath = $null
$metadataPartialPath = $null

try {
    try {
        $lock = [System.IO.File]::Open($lockPath, 'OpenOrCreate', 'ReadWrite', 'None')
    } catch {
        throw "Another Quantrade PostgreSQL backup is already running."
    }
    $timestamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssfffZ")
    $fileName = "$($database.Database)_$timestamp.dump"
    $backupPath = Join-Path $resolvedBackupDirectory $fileName
    $partialPath = "$backupPath.partial"
    $metadataPath = "$backupPath.json"
    $metadataPartialPath = "$metadataPath.partial"
    $arguments = @(
        Get-QuantradeConnectionArguments -DatabaseConfig $database
    ) + @(
        "--format=custom", "--compress=6", "--no-owner", "--no-privileges", "--file=$partialPath"
    )
    Invoke-QuantradePostgresTool -Executable $pgDump -Arguments $arguments -Password $database.Password
    $entryCount = Test-QuantradeBackupArchive -BackupFile $partialPath -PgRestore $pgRestore
    Move-Item -LiteralPath $partialPath -Destination $backupPath -ErrorAction Stop
    $partialPath = $null
    $file = Get-Item -LiteralPath $backupPath
    $sha256 = (Get-FileHash -LiteralPath $backupPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $metadata = [ordered]@{
        contract = "quantrade_postgresql_backup_v1"
        createdAt = [DateTime]::UtcNow.ToString("o")
        database = $database.Database
        host = $database.Host
        port = $database.Port
        file = $file.Name
        bytes = $file.Length
        sha256 = $sha256
        restoreEntries = $entryCount
        pgDumpVersion = (& $pgDump --version | Select-Object -First 1)
        retentionDays = $RetentionDays
        minimumBackups = $MinimumBackups
    }
    $metadata | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $metadataPartialPath -Encoding utf8
    Move-Item -LiteralPath $metadataPartialPath -Destination $metadataPath -ErrorAction Stop
    $metadataPartialPath = $null

    $cutoff = [DateTime]::UtcNow.AddDays(-$RetentionDays)
    $backups = @(Get-ChildItem -LiteralPath $resolvedBackupDirectory -Filter "*.dump" -File | Sort-Object LastWriteTimeUtc -Descending)
    $removed = [System.Collections.Generic.List[string]]::new()
    for ($index = $MinimumBackups; $index -lt $backups.Count; $index++) {
        $candidate = $backups[$index]
        if ($candidate.LastWriteTimeUtc -ge $cutoff) { continue }
        Remove-Item -LiteralPath $candidate.FullName -Force
        $candidateMetadata = "$($candidate.FullName).json"
        if (Test-Path -LiteralPath $candidateMetadata -PathType Leaf) { Remove-Item -LiteralPath $candidateMetadata -Force }
        $removed.Add($candidate.Name)
    }

    [pscustomobject]@{
        Contract = "quantrade_postgresql_backup_v1"
        BackupFile = $backupPath
        MetadataFile = $metadataPath
        Bytes = $file.Length
        Sha256 = $sha256
        RestoreEntries = $entryCount
        RetentionDays = $RetentionDays
        MinimumBackups = $MinimumBackups
        RemovedExpiredBackups = @($removed)
    } | ConvertTo-Json -Depth 4
} finally {
    if ($partialPath -and (Test-Path -LiteralPath $partialPath)) { Remove-Item -LiteralPath $partialPath -Force }
    if ($metadataPartialPath -and (Test-Path -LiteralPath $metadataPartialPath)) { Remove-Item -LiteralPath $metadataPartialPath -Force }
    if ($lock) { $lock.Dispose() }
}

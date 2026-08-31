Set-StrictMode -Version Latest

function Get-QuantradeWorkspaceRoot {
    param([Parameter(Mandatory)][string]$ScriptRoot)
    return (Resolve-Path -LiteralPath (Join-Path $ScriptRoot "..")).Path
}

function Resolve-QuantradePath {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$BasePath,
        [switch]$MustExist
    )
    $candidate = if ([System.IO.Path]::IsPathRooted($Path)) { $Path } else { Join-Path $BasePath $Path }
    if ($MustExist) {
        return (Resolve-Path -LiteralPath $candidate -ErrorAction Stop).Path
    }
    return [System.IO.Path]::GetFullPath($candidate)
}

function Get-QuantradeDatabaseConfig {
    param([Parameter(Mandatory)][string]$EnvFile)
    $line = Get-Content -LiteralPath $EnvFile -ErrorAction Stop |
        Where-Object { $_ -match '^\s*DATABASE_URL=' } |
        Select-Object -First 1
    if (-not $line) { throw "DATABASE_URL is missing from $EnvFile." }
    $value = ($line -replace '^\s*DATABASE_URL=', '').Trim().Trim('"').Trim("'")
    try { $uri = [System.Uri]$value } catch { throw "DATABASE_URL is not a valid PostgreSQL URI." }
    if ($uri.Scheme -notin @('postgres', 'postgresql')) { throw "DATABASE_URL must use the postgres or postgresql scheme." }
    $userParts = $uri.UserInfo.Split(':', 2)
    if ($userParts.Count -ne 2 -or -not $userParts[0]) { throw "DATABASE_URL must include a user and password." }
    $database = $uri.AbsolutePath.TrimStart('/')
    if (-not $database) { throw "DATABASE_URL must include a database name." }
    return [pscustomobject]@{
        Host = $uri.Host
        Port = if ($uri.Port -gt 0) { $uri.Port } else { 5432 }
        User = [System.Uri]::UnescapeDataString($userParts[0])
        Password = [System.Uri]::UnescapeDataString($userParts[1])
        Database = [System.Uri]::UnescapeDataString($database)
    }
}

function Get-QuantradePostgresTool {
    param(
        [Parameter(Mandatory)][string]$Name,
        [string]$PostgresBin
    )
    if ($PostgresBin) {
        $candidate = Join-Path $PostgresBin "$Name.exe"
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return (Resolve-Path -LiteralPath $candidate).Path }
        throw "PostgreSQL tool not found: $candidate"
    }
    $command = Get-Command "$Name.exe" -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $known = 'D:\PostgreSQL\18\bin\' + "$Name.exe"
    if (Test-Path -LiteralPath $known -PathType Leaf) { return $known }
    throw "PostgreSQL tool '$Name.exe' was not found. Pass -PostgresBin with the PostgreSQL bin directory."
}

function Invoke-QuantradePostgresTool {
    param(
        [Parameter(Mandatory)][string]$Executable,
        [Parameter(Mandatory)][string[]]$Arguments,
        [Parameter(Mandatory)][string]$Password,
        [switch]$CaptureOutput
    )
    $hadPassword = Test-Path Env:PGPASSWORD
    $previousPassword = $env:PGPASSWORD
    try {
        $env:PGPASSWORD = $Password
        if ($CaptureOutput) {
            $output = & $Executable @Arguments 2>&1
        } else {
            & $Executable @Arguments
            $output = $null
        }
        if ($LASTEXITCODE -ne 0) { throw "PostgreSQL tool '$([System.IO.Path]::GetFileName($Executable))' failed with exit code $LASTEXITCODE." }
        return $output
    } finally {
        if ($hadPassword) { $env:PGPASSWORD = $previousPassword } else { Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue }
    }
}

function Get-QuantradeConnectionArguments {
    param([Parameter(Mandatory)]$DatabaseConfig, [string]$Database)
    return @(
        "--host=$($DatabaseConfig.Host)",
        "--port=$($DatabaseConfig.Port)",
        "--username=$($DatabaseConfig.User)",
        "--dbname=$(if ($Database) { $Database } else { $DatabaseConfig.Database })"
    )
}

function Test-QuantradeBackupArchive {
    param(
        [Parameter(Mandatory)][string]$BackupFile,
        [Parameter(Mandatory)][string]$PgRestore
    )
    $listing = & $PgRestore --list $BackupFile 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Backup archive validation failed: $BackupFile" }
    $entries = @($listing | Where-Object { $_ -and -not $_.ToString().StartsWith(';') }).Count
    if ($entries -lt 1) { throw "Backup archive contains no restore entries: $BackupFile" }
    return $entries
}

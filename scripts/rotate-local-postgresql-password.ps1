[CmdletBinding(SupportsShouldProcess)]
param([string]$EnvFile = ".env", [string]$PostgresBin)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "postgres-backup-common.ps1")
$workspaceRoot = Get-QuantradeWorkspaceRoot -ScriptRoot $PSScriptRoot
$resolvedEnvFile = Resolve-QuantradePath -Path $EnvFile -BasePath $workspaceRoot -MustExist
if ($resolvedEnvFile -ne (Join-Path $workspaceRoot ".env")) {
    throw "Password rotation is restricted to the repository's exact .env file."
}
$database = Get-QuantradeDatabaseConfig -EnvFile $resolvedEnvFile
if ($database.User -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') {
    throw "PostgreSQL role name is not safe for automated rotation."
}
if (-not $PSCmdlet.ShouldProcess($database.Database, "Rotate the local PostgreSQL role password and update ignored .env")) { return }

$bytes = [byte[]]::new(32)
[Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
$newPassword = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
$uri = [UriBuilder]::new()
$uri.Scheme = "postgresql"
$uri.Host = $database.Host
$uri.Port = $database.Port
$uri.UserName = $database.User
$uri.Password = $newPassword
$uri.Path = $database.Database
$newDatabaseUrl = $uri.Uri.AbsoluteUri
$temporaryEnv = "$resolvedEnvFile.rotating"
$lines = Get-Content -LiteralPath $resolvedEnvFile
$replaced = $false
$updatedLines = foreach ($line in $lines) {
    if ($line -match '^\s*DATABASE_URL=') {
        $replaced = $true
        "DATABASE_URL=$newDatabaseUrl"
    } else {
        $line
    }
}
if (-not $replaced) { throw "DATABASE_URL is missing from .env." }
Set-Content -LiteralPath $temporaryEnv -Value $updatedLines -Encoding utf8

$psql = Get-QuantradePostgresTool -Name "psql" -PostgresBin $PostgresBin
$processInfo = [Diagnostics.ProcessStartInfo]::new()
$processInfo.FileName = $psql
$processInfo.UseShellExecute = $false
$processInfo.RedirectStandardInput = $true
$processInfo.RedirectStandardOutput = $true
$processInfo.RedirectStandardError = $true
$processInfo.Environment["PGPASSWORD"] = $database.Password
foreach ($argument in (Get-QuantradeConnectionArguments -DatabaseConfig $database)) {
    $processInfo.ArgumentList.Add($argument)
}
$processInfo.ArgumentList.Add("--no-psqlrc")
$processInfo.ArgumentList.Add("--set=ON_ERROR_STOP=1")
$quotedRole = '"' + $database.User.Replace('"', '""') + '"'
$sql = "ALTER ROLE $quotedRole PASSWORD '$newPassword';"

try {
    $process = [Diagnostics.Process]::Start($processInfo)
    $process.StandardInput.WriteLine($sql)
    $process.StandardInput.Close()
    $standardOutput = $process.StandardOutput.ReadToEnd()
    $standardError = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) {
        throw "PostgreSQL rejected password rotation: $standardError"
    }
    Move-Item -LiteralPath $temporaryEnv -Destination $resolvedEnvFile -Force
    & (Join-Path $PSScriptRoot "protect-local-secrets.ps1") -EnvFile $resolvedEnvFile | Out-Null
} finally {
    if (Test-Path -LiteralPath $temporaryEnv) { Remove-Item -LiteralPath $temporaryEnv -Force }
    $newPassword = $null
    $sql = $null
}

[pscustomobject]@{
    Contract = "quantrade_postgresql_password_rotation_v1"
    Database = $database.Database
    EnvironmentUpdated = $true
    SecretPrinted = $false
}

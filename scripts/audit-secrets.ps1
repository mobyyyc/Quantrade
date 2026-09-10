[CmdletBinding()]
param([switch]$History)

$ErrorActionPreference = "Stop"
$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$envFile = Join-Path $workspaceRoot ".env"
$tracked = & git -C $workspaceRoot ls-files --error-unmatch .env 2>$null
if ($LASTEXITCODE -eq 0 -or $tracked) { throw ".env is tracked by Git." }
$ignored = & git -C $workspaceRoot check-ignore .env
if ($LASTEXITCODE -ne 0 -or -not $ignored) { throw ".env is not protected by .gitignore." }

$acl = Get-Acl -LiteralPath $envFile
$broadAccess = @($acl.Access | Where-Object {
    $_.IdentityReference.Value -in @("BUILTIN\Users", "NT AUTHORITY\Authenticated Users", "Everyone")
})
if (-not $acl.AreAccessRulesProtected -or $broadAccess.Count -ne 0) {
    throw ".env has inherited or broad Windows access. Run .\scripts\protect-local-secrets.ps1."
}

$previousPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = Join-Path $workspaceRoot "services\research\src"
Push-Location $workspaceRoot
try {
    $arguments = @("-3.14", "-m", "quantrade_research.secret_audit")
    if ($History) { $arguments += "--history" }
    & py @arguments
    if ($LASTEXITCODE -ne 0) { throw "Repository secret audit failed." }
} finally {
    Pop-Location
    $env:PYTHONPATH = $previousPythonPath
}

[pscustomobject]@{
    Contract = "quantrade_secret_audit_v1"
    EnvironmentFileIgnored = $true
    EnvironmentAclProtected = $true
    GitHistoryScanned = [bool]$History
    SecretValuesPrinted = $false
}

[CmdletBinding()]
param([string]$EnvFile = ".env")

$ErrorActionPreference = "Stop"
$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$candidate = if ([IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $workspaceRoot $EnvFile }
$resolvedEnvFile = (Resolve-Path -LiteralPath $candidate -ErrorAction Stop).Path
if ($resolvedEnvFile -ne (Join-Path $workspaceRoot ".env")) {
    throw "Secret protection is restricted to the repository's exact .env file."
}

$currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().User
$system = [Security.Principal.SecurityIdentifier]::new("S-1-5-18")
$administrators = [Security.Principal.SecurityIdentifier]::new("S-1-5-32-544")
$rights = [Security.AccessControl.FileSystemRights]::FullControl
$inheritance = [Security.AccessControl.InheritanceFlags]::None
$propagation = [Security.AccessControl.PropagationFlags]::None
$allow = [Security.AccessControl.AccessControlType]::Allow
$acl = [Security.AccessControl.FileSecurity]::new()
$acl.SetOwner($currentUser)
$acl.SetAccessRuleProtection($true, $false)
foreach ($identity in @($currentUser, $system, $administrators)) {
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($identity, $rights, $inheritance, $propagation, $allow))
}
Set-Acl -LiteralPath $resolvedEnvFile -AclObject $acl

$verified = Get-Acl -LiteralPath $resolvedEnvFile
$broadAccess = @($verified.Access | Where-Object {
    $_.IdentityReference.Value -in @("BUILTIN\Users", "NT AUTHORITY\Authenticated Users", "Everyone")
})
if (-not $verified.AreAccessRulesProtected -or $broadAccess.Count -ne 0) {
    throw "The .env ACL could not be restricted."
}
[pscustomobject]@{
    Contract = "quantrade_local_secret_acl_v1"
    Protected = $verified.AreAccessRulesProtected
    BroadAccessRules = $broadAccess.Count
    SecretValuesPrinted = $false
}

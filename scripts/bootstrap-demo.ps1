[CmdletBinding()]
param(
    [string]$EnvFile = ".env.demo"
)

$ErrorActionPreference = "Stop"
$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$resolvedEnvFile = if ([System.IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $workspaceRoot $EnvFile }
if (-not (Test-Path -LiteralPath $resolvedEnvFile -PathType Leaf)) {
    throw "Demo environment file not found: $resolvedEnvFile. Copy .env.demo.example to .env.demo and set the local PostgreSQL password."
}
foreach ($command in @("node", "corepack", "py")) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) { throw "Required command is unavailable: $command" }
}

Push-Location $workspaceRoot
try {
    Write-Host "Installing the locked web dependencies..."
    & corepack pnpm install --frozen-lockfile
    if ($LASTEXITCODE -ne 0) { throw "Web dependency installation failed." }
    Write-Host "Installing the research package..."
    & py -3.14 -m pip install --disable-pip-version-check -e services/research
    if ($LASTEXITCODE -ne 0) { throw "Research package installation failed." }
    & (Join-Path $PSScriptRoot "setup-demo.ps1") -EnvFile $resolvedEnvFile
    if ($LASTEXITCODE -ne 0) { throw "Synthetic demo setup failed." }
    Write-Host "Demo bootstrap complete. Start it with: .\scripts\run-demo.ps1"
} finally {
    Pop-Location
}

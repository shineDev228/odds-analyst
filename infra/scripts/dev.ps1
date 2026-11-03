<#
.SYNOPSIS
    Démarre l'API et l'interface ODDS ANALYST en mode développement.

.DESCRIPTION
    Ouvre deux fenêtres PowerShell :
      - API FastAPI  : http://localhost:8000
      - Interface    : http://localhost:3000

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File infra/scripts/dev.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path (Join-Path $scriptDir '..\..')
$apiDir = Join-Path $projectRoot 'apps\api'
$webDir = Join-Path $projectRoot 'apps\web'

foreach ($path in @($apiDir, $webDir)) {
    if (-not (Test-Path $path)) { throw "Dossier introuvable : $path" }
}

Write-Host "Démarrage de l'API sur http://localhost:8000 ..."
Start-Process powershell -ArgumentList @(
    '-NoExit',
    '-Command',
    "Set-Location '$apiDir'; uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
)

Start-Sleep -Seconds 3

Write-Host "Démarrage de l'interface sur http://localhost:3100 ..."
Start-Process powershell -ArgumentList @(
    '-NoExit',
    '-Command',
    "Set-Location '$webDir'; npm run dev"
)

Write-Host ""
Write-Host "Interface    : http://localhost:3100"
Write-Host "API          : http://localhost:8000/api/v1/health"
Write-Host "Documentation: http://localhost:8000/docs"
Write-Host ""
Write-Host "Fermer les deux fenêtres pour arrêter l'application." -ForegroundColor Yellow

<#
.SYNOPSIS
    Lance la passe quotidienne de snapshots ODDS ANALYST, application fermee.

.DESCRIPTION
    Deux creneaux, deux roles :

      -Slot morning   faits (statistiques + classements), CSV, puis snapshots
                      des equipes et board marche (06:30)
      -Slot evening   board marche seul, au plus pres de la cloture (18:30)

    Chaque etape ouvre sa propre session et valide son propre commit : l'echec
    de l'une n'annule pas les autres. Le code de sortie est le pire des codes
    rencontres (1 > 3 > 0).

    Le script utilise directement l'environnement virtuel de apps/api : il ne
    depend pas de la commande uv et fonctionne dans une tache planifiee.

    Codes de sortie : 0 applique ou rien a faire, 1 echec, 3 partiel,
    2 argument invalide.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File infra/scripts/snapshots.ps1 -Slot morning

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File infra/scripts/snapshots.ps1 -Slot evening

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File infra/scripts/snapshots.ps1 -Slot morning -Json
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('morning', 'evening')]
    [string]$Slot,
    [string]$Leagues = "",
    [switch]$Force,
    [switch]$Json
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path (Join-Path $scriptDir '..\..')
$apiDir = Join-Path $projectRoot 'apps\api'
$python = Join-Path $apiDir '.venv\Scripts\python.exe'

if (-not (Test-Path $python)) {
    throw "Interpreteur introuvable : $python. Creez l'environnement virtuel de apps/api."
}

$cliArgs = @('-m', 'app.cli', 'snapshots', '--slot', $Slot)
if ($Leagues -ne "") {
    $cliArgs += '--leagues'
    $cliArgs += $Leagues
}
if ($Force) {
    $cliArgs += '--force'
}
if ($Json) {
    $cliArgs += '--json'
}

# Le point d'entree est lance depuis apps/api : les imports et le .env suivent.
$env:PYTHONPATH = "."
$env:PYTHONIOENCODING = "utf-8"

Write-Host ("> python " + ($cliArgs -join ' ')) -ForegroundColor DarkGray
Push-Location $apiDir
try {
    & $python @cliArgs | Out-Host
    $code = $LASTEXITCODE
}
finally {
    Pop-Location
}

if ($code -eq 0) {
    Write-Host "Termine." -ForegroundColor Green
}
else {
    Write-Host ("Termine avec le code " + $code + ".") -ForegroundColor Yellow
}
exit $code

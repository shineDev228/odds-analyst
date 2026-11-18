<#
.SYNOPSIS
    Lance une synchronisation ODDS ANALYST sans navigateur.

.DESCRIPTION
    Une seule action par execution :

      (defaut)    faits BigBallsData : calendrier, resultats, classements
      -Stats      ajoute les statistiques (20 rencontres par competition)
      -Csv        telecharge les fichiers CSV puis importe xG et cloture
      -Odds       apercu gratuit des cotes 1xBet (aucun credit consomme)
      -OddsImport importe les cotes 1xBet (CREDITS PAYANTS, action explicite)
      -Status     etat des trois sources, lecture seule, aucun appel reseau

    Le script se place lui-meme dans apps/api : il peut etre lance depuis
    n'importe quel dossier, y compris par le Planificateur de taches Windows.

    Codes de sortie : 0 applique ou rien a faire, 1 echec, 3 partiel,
    2 argument invalide.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File infra/scripts/sync.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File infra/scripts/sync.ps1 -Stats -Standings

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File infra/scripts/sync.ps1 -Csv -Json
#>

[CmdletBinding()]
param(
    [switch]$Csv,
    [switch]$Odds,
    [switch]$OddsImport,
    [switch]$Status,
    [switch]$Stats,
    [switch]$Standings,
    [string]$Leagues = "",
    [switch]$Json
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path (Join-Path $scriptDir '..\..')
$apiDir = Join-Path $projectRoot 'apps\api'

if (-not (Test-Path $apiDir)) {
    throw "Dossier introuvable : $apiDir"
}

$actions = @($Csv, $Odds, $OddsImport, $Status) | Where-Object { $_ }
if ($actions.Count -gt 1) {
    throw "Choisissez une seule action : -Csv, -Odds, -OddsImport ou -Status."
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "La commande 'uv' est introuvable. Installez uv puis relancez le script."
}

function Invoke-Cli {
    param([string[]]$CliArgs)

    Write-Host ("> python -m app.cli " + ($CliArgs -join ' ')) -ForegroundColor DarkGray
    Push-Location $apiDir
    try {
        & uv run python -m app.cli @CliArgs | Out-Host
        $code = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    return $code
}

$jsonArgs = @()
if ($Json) {
    $jsonArgs += '--json'
}
$leagueArgs = @()
if ($Leagues -ne "") {
    $leagueArgs += '--leagues'
    $leagueArgs += $Leagues
}

$codes = @()
if ($Status) {
    $codes += Invoke-Cli (@('status') + $jsonArgs)
}
elseif ($Csv) {
    $download = Invoke-Cli (@('csv-download') + $leagueArgs + $jsonArgs)
    $codes += $download
    if ($download -eq 0 -or $download -eq 3) {
        $codes += Invoke-Cli (@('csv-import') + $leagueArgs + $jsonArgs)
    }
}
elseif ($Odds) {
    $codes += Invoke-Cli (@('odds-preview') + $leagueArgs + $jsonArgs)
}
elseif ($OddsImport) {
    $codes += Invoke-Cli (@('odds-import') + $leagueArgs + $jsonArgs)
}
else {
    $factsArgs = @('facts')
    if ($Stats) {
        $factsArgs += '--stats'
        $factsArgs += '--stats-limit'
        $factsArgs += '20'
    }
    if ($Standings) {
        $factsArgs += '--standings'
    }
    $codes += Invoke-Cli ($factsArgs + $leagueArgs + $jsonArgs)
}

$final = 0
foreach ($code in $codes) {
    if ($code -eq 1) {
        $final = 1
    }
    elseif ($code -ne 0 -and $final -eq 0) {
        $final = $code
    }
}

if ($final -eq 0) {
    Write-Host "Termine." -ForegroundColor Green
}
else {
    Write-Host ("Termine avec le code " + $final + ".") -ForegroundColor Yellow
}
exit $final

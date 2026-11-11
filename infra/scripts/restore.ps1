<#
.SYNOPSIS
    Restaure une sauvegarde ODDS ANALYST dans une base de test.

.DESCRIPTION
    - Lit les paramètres de connexion depuis .env (aucun mot de passe affiché).
    - Restaure par défaut dans `odds_analyst_restore_test`, jamais dans la base
      de travail : la restauration détruit le contenu de la base cible.
    - Recrée la base cible avant la restauration.
    - Vérifie que les tables principales contiennent des données.
    - Exige une confirmation explicite pour viser la base réelle.

.PARAMETER BackupFile
    Chemin de l'archive produite par backup.ps1 (.dump).

.PARAMETER TargetDatabase
    Base cible. Par défaut `odds_analyst_restore_test`.

.PARAMETER ForceProduction
    Autorise la restauration dans la base réelle. Une confirmation saisie à la
    main reste obligatoire.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File infra/scripts/restore.ps1 -BackupFile infra/backups/odds_analyst-20261110-210000.dump

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File infra/scripts/restore.ps1 -BackupFile .\sauvegarde.dump -TargetDatabase odds_analyst_verif
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BackupFile,

    [string]$TargetDatabase = 'odds_analyst_restore_test',

    [switch]$ForceProduction
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path (Join-Path $scriptDir '..\..')
$envFile = Join-Path $projectRoot '.env'

if (-not (Test-Path $envFile)) { throw "Fichier .env introuvable." }

# --- Lecture du .env --------------------------------------------------------
$config = @{}
Get-Content $envFile | Where-Object { $_ -match '^\s*[^#].*=' } | ForEach-Object {
    $parts = $_ -split '=', 2
    $config[$parts[0].Trim()] = $parts[1].Trim()
}

$prodDb = $config['POSTGRES_DB']
$dbUser = $config['POSTGRES_USER']
$dbPass = $config['POSTGRES_PASSWORD']
$dbHost = if ($config['POSTGRES_HOST']) { $config['POSTGRES_HOST'] } else { 'localhost' }
$dbPort = if ($config['POSTGRES_PORT']) { $config['POSTGRES_PORT'] } else { '5432' }

# Rôle autorisé à créer des bases. Par défaut le compte applicatif ; sur une
# installation locale, renseigner POSTGRES_ADMIN_USER=postgres dans .env (ou
# dans l'environnement) avec un rôle disposant du droit CREATEDB.
$adminUser = if ($config['POSTGRES_ADMIN_USER']) {
    $config['POSTGRES_ADMIN_USER']
} elseif ($env:POSTGRES_ADMIN_USER) {
    $env:POSTGRES_ADMIN_USER
} else {
    $dbUser
}
$adminPass = if ($config['POSTGRES_ADMIN_PASSWORD']) {
    $config['POSTGRES_ADMIN_PASSWORD']
} elseif ($env:POSTGRES_ADMIN_PASSWORD) {
    $env:POSTGRES_ADMIN_PASSWORD
} else {
    $dbPass
}

if (-not $prodDb -or -not $dbUser) { throw "POSTGRES_DB ou POSTGRES_USER absent du .env." }

# --- Contrôles de sécurité --------------------------------------------------
if ($TargetDatabase -notmatch '^[A-Za-z0-9_]+$') {
    throw "Nom de base invalide : lettres, chiffres et tirets bas uniquement."
}
if ($TargetDatabase -in @('postgres', 'template0', 'template1')) {
    throw "La base système '$TargetDatabase' ne peut pas être une cible."
}

$archive = Resolve-Path -LiteralPath $BackupFile -ErrorAction SilentlyContinue
if (-not $archive) { throw "Sauvegarde introuvable : $BackupFile" }
$archive = $archive.Path
if (-not $archive.EndsWith('.dump')) {
    throw "Le fichier doit être une archive .dump produite par backup.ps1."
}
if ((Get-Item $archive).Length -lt 1024) {
    throw "Sauvegarde suspecte : moins de 1 Ko."
}

if ($TargetDatabase -eq $prodDb) {
    if (-not $ForceProduction) {
        throw "Refus de restaurer dans la base réelle '$prodDb'. Utilisez -TargetDatabase pour une base de test, ou -ForceProduction en connaissance de cause."
    }
    Write-Warning "La base cible est la base réelle : toutes ses données seront remplacées."
    $confirmation = Read-Host "Saisissez le nom de la base ($prodDb) pour confirmer"
    if ($confirmation -ne $prodDb) { throw "Confirmation incorrecte. Restauration annulée." }
}

# --- Localisation des outils PostgreSQL -------------------------------------
function Find-PgTool([string]$Name) {
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = Get-ChildItem 'C:\Program Files\PostgreSQL' -Directory -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending |
        ForEach-Object { Join-Path $_.FullName "bin\$Name" } |
        Where-Object { Test-Path $_ }
    if ($candidates) { return $candidates | Select-Object -First 1 }
    throw "$Name introuvable."
}

$psql = Find-PgTool 'psql.exe'
$pgRestore = Find-PgTool 'pg_restore.exe'

$env:PGPASSWORD = $adminPass
try {
    # --- Recréation de la base cible ---------------------------------------
    Write-Host "Préparation de la base cible '$TargetDatabase' ..."
    $sql = @"
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = '$TargetDatabase' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS "$TargetDatabase";
CREATE DATABASE "$TargetDatabase" OWNER "$dbUser";
"@
    $sql | & $psql -h $dbHost -p $dbPort -U $adminUser -d postgres -v ON_ERROR_STOP=1 -q -t -A 2>$null
    if ($LASTEXITCODE -ne 0) { throw "Échec de la préparation de la base (code $LASTEXITCODE)." }
}
finally {
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
}

$env:PGPASSWORD = $dbPass
try {
    # --- Restauration -------------------------------------------------------
    Write-Host "Restauration de $archive ..."
    & $pgRestore -h $dbHost -p $dbPort -U $dbUser -d $TargetDatabase `
        --clean --if-exists --no-owner --no-privileges --exit-on-error $archive
    if ($LASTEXITCODE -ne 0) { throw "Échec de pg_restore (code $LASTEXITCODE)." }

    # --- Vérification -------------------------------------------------------
    $counts = & $psql -h $dbHost -p $dbPort -U $dbUser -d $TargetDatabase -t -A `
        -c "SELECT (SELECT count(*) FROM matches), (SELECT count(*) FROM teams), (SELECT count(*) FROM users);"
    if ($LASTEXITCODE -ne 0) { throw "Échec de la vérification (code $LASTEXITCODE)." }

    $parts = ($counts -join '').Trim().Split('|')
    $matches = [int]$parts[0]
    $teams = [int]$parts[1]

    if ($matches -le 0) { throw "Restauration incomplète : aucune rencontre restaurée." }

    Write-Host ("Restauration réussie dans '{0}' : {1} rencontres, {2} équipes." -f `
        $TargetDatabase, $matches, $teams) -ForegroundColor Green
    Write-Host "Pour vérifier l'application sur cette base, changez temporairement POSTGRES_DB/DATABASE_URL dans .env, puis redémarrez l'API."
}
finally {
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
}

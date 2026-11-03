<#
.SYNOPSIS
    Sauvegarde la base ODDS ANALYST avec pg_dump.

.DESCRIPTION
    - Lit les paramètres de connexion depuis .env.
    - Produit une archive compressée horodatée dans infra/backups.
    - Supprime les archives de plus de 30 jours.
    - Vérifie que la sauvegarde n'est pas vide.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File infra/scripts/backup.ps1
#>

[CmdletBinding()]
param(
    [int]$RetentionDays = 30
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path (Join-Path $scriptDir '..\..')
$envFile = Join-Path $projectRoot '.env'
$backupDir = Join-Path $projectRoot 'infra\backups'

if (-not (Test-Path $envFile)) { throw "Fichier .env introuvable." }
if (-not (Test-Path $backupDir)) { New-Item -ItemType Directory -Path $backupDir | Out-Null }

# --- Lecture du .env --------------------------------------------------------
$config = @{}
Get-Content $envFile | Where-Object { $_ -match '^\s*[^#].*=' } | ForEach-Object {
    $parts = $_ -split '=', 2
    $config[$parts[0].Trim()] = $parts[1].Trim()
}

$dbName = $config['POSTGRES_DB']
$dbUser = $config['POSTGRES_USER']
$dbPass = $config['POSTGRES_PASSWORD']
$dbHost = if ($config['POSTGRES_HOST']) { $config['POSTGRES_HOST'] } else { 'localhost' }
$dbPort = if ($config['POSTGRES_PORT']) { $config['POSTGRES_PORT'] } else { '5432' }

# --- Localisation de pg_dump ------------------------------------------------
function Find-PgDump {
    $cmd = Get-Command pg_dump.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = Get-ChildItem 'C:\Program Files\PostgreSQL' -Directory -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending |
        ForEach-Object { Join-Path $_.FullName 'bin\pg_dump.exe' } |
        Where-Object { Test-Path $_ }
    if ($candidates) { return $candidates | Select-Object -First 1 }
    throw "pg_dump.exe introuvable."
}

$pgDump = Find-PgDump
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$target = Join-Path $backupDir "odds_analyst-$stamp.dump"

$env:PGPASSWORD = $dbPass
try {
    Write-Host "Sauvegarde de $dbName vers $target ..."
    & $pgDump -h $dbHost -p $dbPort -U $dbUser -d $dbName -F c -Z 9 -f $target
    if ($LASTEXITCODE -ne 0) { throw "Échec de pg_dump (code $LASTEXITCODE)." }
}
finally {
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
}

$size = (Get-Item $target).Length
if ($size -lt 1024) { throw "Sauvegarde suspecte : $size octets." }

Write-Host ("Sauvegarde réussie : {0:N0} octets" -f $size) -ForegroundColor Green

# --- Purge des anciennes sauvegardes ---------------------------------------
$limit = (Get-Date).AddDays(-$RetentionDays)
Get-ChildItem $backupDir -Filter '*.dump' |
    Where-Object { $_.LastWriteTime -lt $limit } |
    ForEach-Object {
        Write-Host "Suppression de l'ancienne sauvegarde $($_.Name)"
        Remove-Item $_.FullName -Force
    }

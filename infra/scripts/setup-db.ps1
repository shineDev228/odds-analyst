<#
.SYNOPSIS
    Crée le rôle applicatif et la base de données ODDS ANALYST.

.DESCRIPTION
    - Localise psql.exe (PATH ou dossier d'installation PostgreSQL).
    - Génère un mot de passe applicatif aléatoire si nécessaire.
    - Crée le rôle « odds_analyst_app » avec des droits limités.
    - Crée la base « odds_analyst ».
    - Écrit les valeurs dans le fichier .env du projet (sans écraser un .env existant).

.PARAMETER SuperPassword
    Mot de passe du superutilisateur « postgres ».
    Si omis, le script tente PGPASSWORD puis demande une saisie sécurisée.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File infra/scripts/setup-db.ps1
#>

[CmdletBinding()]
param(
    [string]$SuperPassword
)

$ErrorActionPreference = 'Stop'

# --- Localisation de la racine du projet -----------------------------------
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path (Join-Path $scriptDir '..\..')
$envFile = Join-Path $projectRoot '.env'
$envExample = Join-Path $projectRoot '.env.example'

Write-Host "Projet : $projectRoot"

# --- Localisation de psql ---------------------------------------------------
function Find-Psql {
    $cmd = Get-Command psql.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    $candidates = Get-ChildItem 'C:\Program Files\PostgreSQL' -Directory -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending |
        ForEach-Object { Join-Path $_.FullName 'bin\psql.exe' } |
        Where-Object { Test-Path $_ }

    if ($candidates) { return $candidates | Select-Object -First 1 }
    throw "psql.exe introuvable. PostgreSQL est-il installé ?"
}

$psql = Find-Psql
Write-Host "psql   : $psql"

# --- Génération des secrets ------------------------------------------------
function New-RandomToken {
    param([int]$ByteCount)

    $bytes = New-Object byte[] $ByteCount
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return [Convert]::ToBase64String($bytes).Replace('+', '-').Replace('/', '_').TrimEnd('=')
}

function New-FernetKey {
    # Clé Fernet : 32 octets encodés en base64 urlsafe, padding conservé.
    param([int]$ByteCount = 32)

    $bytes = New-Object byte[] $ByteCount
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return [Convert]::ToBase64String($bytes).Replace('+', '-').Replace('/', '_')
}

function New-AppPassword { return New-RandomToken -ByteCount 24 }

$dbName = 'odds_analyst'
$dbUser = 'odds_analyst_app'
$appPassword = New-AppPassword

# --- Authentification du superutilisateur ----------------------------------
if (-not $SuperPassword) {
    if ($env:PGPASSWORD) {
        $SuperPassword = $env:PGPASSWORD
    }
    else {
        Write-Host ""
        Write-Host "Mot de passe du superutilisateur PostgreSQL « postgres » requis." -ForegroundColor Yellow
        $secure = Read-Host -AsSecureString "Saisissez-le (il ne sera pas affiché)"
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try { $SuperPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    }
}

# --- Exécution SQL ----------------------------------------------------------
$sql = @"
DO `$`$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$dbUser') THEN
        CREATE ROLE $dbUser LOGIN PASSWORD '$appPassword';
    ELSE
        ALTER ROLE $dbUser WITH LOGIN PASSWORD '$appPassword';
    END IF;
END
`$`$;
"@

$tempSql = [System.IO.Path]::GetTempFileName()
Set-Content -Path $tempSql -Value $sql -Encoding UTF8

try {
    $env:PGPASSWORD = $SuperPassword
    Write-Host "Création du rôle applicatif..."
    & $psql -U postgres -h localhost -p 5432 -d postgres -v ON_ERROR_STOP=1 -f $tempSql
    if ($LASTEXITCODE -ne 0) { throw "Échec de la création du rôle (code $LASTEXITCODE)." }

    $dbExists = & $psql -U postgres -h localhost -p 5432 -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$dbName'"
    if ($dbExists -ne '1') {
        Write-Host "Création de la base $dbName..."
        & $psql -U postgres -h localhost -p 5432 -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE $dbName OWNER $dbUser ENCODING 'UTF8' LC_COLLATE 'French_France.1252' LC_CTYPE 'French_France.1252' TEMPLATE template0;"
        if ($LASTEXITCODE -ne 0) { throw "Échec de la création de la base (code $LASTEXITCODE)." }
    }
    else {
        Write-Host "La base $dbName existe déjà."
    }

    Write-Host "Attribution des droits sur le schéma public..."
    & $psql -U postgres -h localhost -p 5432 -d $dbName -v ON_ERROR_STOP=1 -c "GRANT ALL ON SCHEMA public TO $dbUser;"
}
finally {
    Remove-Item $tempSql -Force -ErrorAction SilentlyContinue
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
}

# --- Écriture du fichier .env ----------------------------------------------
if (-not (Test-Path $envFile)) {
    Copy-Item $envExample $envFile
    Write-Host "Fichier .env créé à partir de .env.example." -ForegroundColor Green
}

$content = Get-Content $envFile -Raw
$content = $content -replace 'POSTGRES_PASSWORD=.*', "POSTGRES_PASSWORD=$appPassword"
$content = $content -replace 'DATABASE_URL=.*', "DATABASE_URL=postgresql+psycopg://$dbUser`:$appPassword@localhost:5432/$dbName"
$content = $content -replace 'SECRET_KEY=.*', ("SECRET_KEY=" + (New-RandomToken -ByteCount 48))
$content = $content -replace 'ENCRYPTION_KEY=.*', ("ENCRYPTION_KEY=" + (New-FernetKey))
Set-Content -Path $envFile -Value $content -Encoding UTF8 -NoNewline

Write-Host ""
Write-Host "Base de données prête." -ForegroundColor Green
Write-Host "  Base       : $dbName"
Write-Host "  Rôle       : $dbUser"
Write-Host "  Mot de passe : enregistré dans .env (ne pas commiter)"

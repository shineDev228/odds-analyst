# ODDS ANALYST

Application web personnelle d'analyse statistique sportive.

> **ODDS ANALYST est un outil d'analyse.**
> Il ne prédit pas l'issue des rencontres et ne garantit aucun résultat.
> Les cotes élevées impliquent un risque élevé de perte totale.
> Aucun pari n'est placé automatiquement.

---

## État du projet

| Phase | Statut |
|---|---|
| 0 — Environnement et squelette | 🔄 En cours |
| 1 — Socle (authentification, rencontres) | ⬜ À venir |
| 2 — Marchés et cotes | ⬜ À venir |
| 3 — Moteur statistique v1 | ⬜ À venir |
| 4 — Générateur de combinaisons | ⬜ À venir |
| 5 — Historique et performance | ⬜ À venir |
| 6 — Moteur statistique v2 | ⬜ À venir |
| 7 — Connecteurs de données | ⬜ À venir |
| 8 — Durcissement et documentation | ⬜ À venir |

---

## Prérequis

| Outil | Version minimale | Rôle |
|---|---|---|
| Node.js | 24 LTS | Interface web |
| Python | 3.12 | API et moteur statistique |
| PostgreSQL | 16 | Base de données |
| uv | 0.5 | Gestion de l'environnement Python |
| Git | 2.40 | Versionnement du code |

---

## Démarrage (3 étapes)

### 1. Configuration

```powershell
Copy-Item .env.example .env
```

Puis renseigner les valeurs `a_generer` dans `.env`
(voir les commentaires du fichier).

### 2. Base de données

```powershell
powershell -ExecutionPolicy Bypass -File infra/scripts/setup-db.ps1
```

### 3. Lancer l'application

```powershell
powershell -ExecutionPolicy Bypass -File infra/scripts/dev.ps1
```

| Service | Adresse |
|---|---|
| Interface | http://localhost:3100 |
| API | http://localhost:8000 |
| Documentation API | http://localhost:8000/docs |

> Les ports **3100** (interface) et **8000** (API) sont réservés à ODDS ANALYST.
> Le port 3000 est volontairement évité : il est déjà utilisé par une autre
> application sur cette machine.

---

## Structure du dépôt

```
apps/
  web/         Interface Next.js (aucun calcul statistique)
  api/         API FastAPI
    app/       Orchestration, validation, persistance
    engine/    Moteur statistique pur (sans base de données ni réseau)
docs/
  adr/         Décisions d'architecture documentées
infra/
  scripts/     Installation, démarrage, sauvegarde
```

### Règle d'architecture fondamentale

Le dossier `apps/api/engine/` ne doit **jamais** importer SQLAlchemy, FastAPI
ou un client HTTP. Il contient des fonctions pures, testables isolément.
Cette contrainte garantit la fiabilité et la reproductibilité des calculs.

---

## Tests

```powershell
# API et moteur
uv run pytest

# Interface
npm run lint
```

---

## Licence et usage

Projet privé, usage strictement personnel.
Aucun scraping non autorisé, aucune automatisation de pari,
aucun stockage d'identifiants de bookmaker.

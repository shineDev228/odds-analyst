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
| 0 — Environnement et squelette | ✅ Terminée |
| 1 — Socle (authentification, rencontres) | ✅ Terminée |
| 2 — Marchés et cotes | ✅ Terminée |
| 3 — Moteur statistique v1 | ✅ Terminée |
| 4 — Générateur de combinaisons | ✅ Terminée |
| 5 — Historique et performance | 🟡 Implémentée — à valider |
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

## Fonctionnalités disponibles

- **Authentification** : compte unique, mot de passe haché avec Argon2id, sessions
  serveur, cookie `httpOnly`, protection CSRF par double soumission et limitation
  des tentatives de connexion.
- **Référentiel** : sports (football fourni), compétitions, saisons, équipes.
- **Rencontres** : création, modification, suppression, filtres par compétition,
  équipe, statut et période.
- **Statistiques** : saisie manuelle par équipe (buts, tirs, possession, corners,
  cartons, buts attendus).
- **Marchés et cotes** : catalogue extensible adapté à chaque sport (résultat,
  handicaps, totaux, corners, cartons, marchés joueurs, combinés…), création de
  marchés personnalisés, relevés de cotes horodatés jamais écrasés, historique,
  marge du bookmaker, probabilités implicites et cotes équitables.
- **Analyse statistique (football)** : probabilités estimées pour le 1X2, la
  double chance, les totaux de buts, « les deux équipes marquent » et les scores
  exacts. Chaque probabilité est accompagnée d'une fourchette à 80 % issue d'une
  simulation Monte Carlo déterministe. Le niveau de fiabilité et les limites du
  modèle sont affichés ; l'analyse est refusée si l'historique est trop court.
- **Générateur de combinaisons (football)** : assemblages de 2 à 15 sélections
  issus des rencontres à venir, une seule sélection par rencontre, cote totale
  dans la fourchette visée. Chaque résultat affiche la cote totale, la
  probabilité estimée, la fourchette à 80 % et l'espérance estimée. Les
  rencontres sans cote récente ou sans historique suffisant sont ignorées et
  comptées. Aucune combinaison n'est présentée comme certaine.
- **Historique et performance** : enregistrement d'une combinaison générée avec
  ses cotes et ses estimations, règlement automatique des sélections (1X2,
  double chance, plus / moins), suivi des statuts (en attente, gagnée, perdue,
  remboursée, indisponible) et synthèse en unités de mise : taux de réussite,
  résultat net et ROI. Les cotes enregistrées sont figées ; le statut est
  recalculé à partir du score actuel. Aucun montant en argent, aucune
  recommandation de mise.
- **Tableau de bord** : indicateurs et prochaines rencontres.
- **Paramètres** : fourchette de cotes 50–100, nombre de sélections, marchés
  autorisés, demi-vie de pondération.

### Modèle statistique v1

Le moteur (`apps/api/engine/`) estime des forces d'attaque et de défense à
partir des buts marqués et encaissés, avec pondération temporelle (demi-vie),
régularisation vers la moyenne et avantage du terrain. Les scores suivent une
loi de Poisson bivariée corrigée par Dixon-Coles. Les buts attendus, les
probabilités et leurs fourchettes sont calculés sans appel réseau ni accès à la
base : le service se contente de fournir l'historique.

Le modèle v1 reste volontairement simple : il n'utilise ni xG, ni compositions,
ni blessures, ni enjeu sportif, et ne couvre que le football. Il exige au moins
**3 matchs terminés par équipe** avant le coup d'envoi ; sinon l'API répond
`409` avec un message explicite plutôt que d'inventer une probabilité.

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

## Tests et qualité

```powershell
# API et moteur (94 tests)
uv run pytest

# Analyse statique du code Python
uv run ruff check .
uv run mypy app engine

# Interface
npm run lint
npm run typecheck
```

L'interface appelle l'API via le proxy Next.js `/api` (voir
`apps/web/next.config.ts`) : cookies et jeton CSRF restent en même origine.
Si l'API tourne ailleurs que sur `http://127.0.0.1:8000`, définir la variable
d'environnement `API_URL` avant de démarrer l'interface.

---

## Licence et usage

Projet privé, usage strictement personnel.
Aucun scraping non autorisé, aucune automatisation de pari,
aucun stockage d'identifiants de bookmaker.

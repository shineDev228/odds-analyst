# ODDS ANALYST

[![CI](https://github.com/shineDev228/odds-analyst/actions/workflows/ci.yml/badge.svg)](https://github.com/shineDev228/odds-analyst/actions/workflows/ci.yml)

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
| 5 — Historique et performance | ✅ Terminée |
| 6 — Moteur statistique v2 | ✅ Terminée |
| 7 — Connecteurs de données | ✅ Terminée |
| 8 — Durcissement et documentation | ✅ Terminée |
| 9 — Appariement des noms et performance | ✅ Terminée |
| 10 — Marché « les deux équipes marquent » | ✅ Terminée |
| 11 — Fenêtre de calendrier des connecteurs | ✅ Terminée |
| 12 — Combinaisons limitées au jour | ✅ Terminée |
| 13 — Cotes 1X2 dans la liste des rencontres | ✅ Terminée |

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
  dans la fourchette visée. Marchés disponibles : 1X2, double chance,
  plus / moins de buts et « les deux équipes marquent ». Chaque résultat affiche
  la cote totale, la probabilité estimée, la fourchette à 80 % et l'espérance
  estimée. Les rencontres sans cote récente ou sans historique suffisant sont
  ignorées et comptées. Aucune combinaison n'est présentée comme certaine.
- **Historique et performance** : enregistrement d'une combinaison générée avec
  ses cotes et ses estimations, règlement automatique des sélections (1X2,
  double chance, plus / moins, les deux équipes marquent), suivi des statuts
  (en attente, gagnée, perdue, remboursée, indisponible) et synthèse en unités
  de mise : taux de réussite, résultat net et ROI. Les cotes enregistrées sont
  figées ; le statut est recalculé à partir du score actuel. Aucun montant en
  argent, aucune recommandation de mise.
- **Calibration** : rétro-test honnête des prévisions 1X2 passées, avec score de
  Brier, log loss, précision, compétence par rapport aux fréquences de base,
  erreur de calibration (ECE) et tableau de fiabilité par tranches. Chaque
  rencontre est pronostiquée avec l'historique strictement antérieur à son coup
  d'envoi ; les rencontres non évaluables sont exclues et comptées.
- **Tableau de bord** : indicateurs et prochaines rencontres.
- **Connecteurs de données** : import du calendrier et des résultats via
  football-data.org, des statistiques (xG, tirs cadrés, corners, cartons) via
  les fichiers CSV publics de football-data.co.uk — sans clé ni quota — et des
  cotes 1xBet agrégées via The Odds API (1X2, totaux, double chance, « les deux
  équipes marquent »). Chaque import commence par un aperçu stocké deux heures
  et ne s'applique qu'après validation. Les quotas gratuits sont suivis
  localement. Le score exact et le handicap restent manuels ; si 1xBet est
  absent, aucune cote n'est inventée et aucun autre bookmaker ne le remplace.
  Une correction manuelle n'est jamais écrasée. Ordre conseillé :
  **calendrier → résultats et statistiques (CSV) → cotes**.
- **Sécurité et exploitation** : en-têtes de sécurité, CSP par nonce en
  production, expiration d'inactivité de 12 h, purge des sessions, journal JSON
  avec identifiant de requête, sauvegarde et restauration vérifiée dans une base
  de test.
- **Paramètres** : fourchette de cotes 50–100, nombre de sélections, marchés
  autorisés, demi-vie de pondération.

### Modèle statistique v2

Le moteur (`apps/api/engine/`) estime des forces d'attaque et de défense à
partir des buts marqués et encaissés, complétés par le **xG saisi** ou, à
défaut, par un **proxy fondé sur les tirs cadrés** (`0,30 × tirs cadrés`,
plafonné à 4,0). Sans statistique, la rencontre utilise les buts réels : aucune
valeur n'est inventée. La couverture statistique est affichée par équipe et un
avertissement apparaît sous 50 %.

Les scores suivent une loi de Poisson bivariée corrigée par Dixon-Coles, dont
le paramètre `rho` est désormais **estimé puis rétréci vers un prior** pour
protéger les petits échantillons. La pondération temporelle (demi-vie), la
régularisation vers la moyenne et l'avantage du terrain restent en place. Les
calculs se font sans appel réseau ni accès à la base.

Le modèle reste volontairement explicable : il n'utilise ni compositions, ni
blessures, ni enjeu sportif, et ne couvre que le football. Ces éléments, ainsi
que la force du championnat, restent hors périmètre : aucune source gratuite
fiable ne les fournit. Le moteur exige toujours au moins **3 matchs terminés par
équipe** avant le coup d'envoi ; sinon l'API répond `409` avec un message
explicite plutôt que d'inventer une probabilité.

---

## Guide utilisateur

Le parcours complet, écran par écran, de la création du référentiel à la
génération des combinaisons est décrit dans
[`docs/guide-utilisation.md`](docs/guide-utilisation.md) : prérequis, saisie des
cotes, lecture des fourchettes, critères du générateur, dépannage et check-list.

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
  exploitation/ Sauvegarde, restauration, sécurité, dépannage, API
  phases/      Journal des phases et décisions
infra/
  scripts/     Installation, démarrage, sauvegarde, restauration
  backups/     Archives locales (exclues de Git)
```

### Règle d'architecture fondamentale

Le dossier `apps/api/engine/` ne doit **jamais** importer SQLAlchemy, FastAPI
ou un client HTTP. Il contient des fonctions pures, testables isolément.
Cette contrainte garantit la fiabilité et la reproductibilité des calculs.

---

## Tests et qualité

```powershell
# API et moteur (241 tests)
uv run pytest

# Analyse statique du code Python
uv run ruff check .
uv run mypy app engine

# Interface
npm run lint
npm run typecheck
npm run build
```

L'interface appelle l'API via le proxy Next.js `/api` (voir
`apps/web/next.config.ts`) : cookies et jeton CSRF restent en même origine.
Si l'API tourne ailleurs que sur `http://127.0.0.1:8000`, définir la variable
d'environnement `API_URL` avant de démarrer l'interface.

### Intégration continue

Le workflow [`.github/workflows/ci.yml`](.github/workflows/ci.yml) rejoue ces
vérifications à chaque envoi sur `main` :

| Job | Contenu |
|---|---|
| API et moteur statistique | `ruff`, `mypy app engine`, `pytest` |
| Interface Next.js | `eslint`, `tsc --noEmit`, `next build` |

Les tests s'exécutent sur une base SQLite en mémoire : la CI ne se connecte ni
à PostgreSQL, ni à un fournisseur de données, et n'utilise aucun secret.

## Sécurité et exploitation

| Sujet | Document |
|---|---|
| En-têtes, CSP, sessions, CSRF, clés | `docs/exploitation/securite.md` |
| Sauvegarde et restauration vérifiée | `docs/exploitation/sauvegarde-restauration.md` |
| Pannes courantes, ports, quotas | `docs/exploitation/depannage.md` |
| Routes et erreurs de l'API | `docs/exploitation/api.md` |
| Phase 8 : décisions et tests | `docs/phases/phase-8-durcissement.md` |
| Phase 9 : appariement et performance | `docs/phases/phase-9-appariement-performance.md` |
| Phase 10 : marché « les deux équipes marquent » | `docs/phases/phase-10-btts.md` |
| Phase 11 : fenêtre de calendrier | `docs/phases/phase-11-fenetre-calendrier.md` |
| Phase 12 : combinaisons du jour | `docs/phases/phase-12-combinaisons-du-jour.md` |
| Phase 13 : cotes 1X2 dans la liste | `docs/phases/phase-13-cotes-liste-rencontres.md` |

Commandes utiles :

```powershell
# Sauvegarde
powershell -ExecutionPolicy Bypass -File infra/scripts/backup.ps1

# Restauration dans une base de test (jamais la base réelle par défaut)
powershell -ExecutionPolicy Bypass -File infra/scripts/restore.ps1 `
  -BackupFile infra\backups\odds_analyst-AAAAMMJJ-HHMMSS.dump
```

---

## Licence et usage

Projet personnel, publié publiquement à titre de démonstration technique.
Aucune licence n'est accordée : tous droits réservés. Le code peut être lu et
cité, mais ni réutilisé, ni modifié, ni redistribué sans autorisation écrite.
Aucun scraping non autorisé, aucune automatisation de pari,
aucun stockage d'identifiants de bookmaker.

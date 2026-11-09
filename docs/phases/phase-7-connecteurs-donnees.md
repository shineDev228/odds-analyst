# Phase 7 — Connecteurs de données

> **Statut : plan révisé — en attente de validation.** Import automatique du
> calendrier, des résultats, des statistiques et des **cotes 1xBet** via une
> combinaison de sources gratuites et autorisées. La saisie manuelle reste
> disponible comme secours et correction.

## Objectif

Réduire la saisie manuelle sans jamais dépendre d'une source unique :

1. **Calendrier et résultats** : importer les rencontres, leur statut, leur
   score et leur coup d'envoi.
2. **Statistiques d'équipe** : importer tirs, tirs cadrés, possession, corners,
   cartons, passes ; le xG seulement s'il est réellement fourni.
3. **Cotes 1xBet** : importer les marchés réellement proposés par le
   fournisseur, avec le bookmaker `1xBet` et une source explicite.
4. **Traçabilité** : distinguer à tout moment une donnée importée d'une donnée
   saisie, et ne jamais écraser silencieusement une correction manuelle.
5. **Sobriété** : budgets locaux stricts, coût affiché avant chaque appel,
   aucun appel réseau déclenché sans confirmation.

L'import augmente la **couverture** et le **volume** des données. Il ne rend pas
le modèle plus certain, ne garantit aucun résultat et ne constitue pas un
conseil de pari.

## La combinaison retenue

Aucun fournisseur gratuit ne réunit à lui seul la saison en cours, les
statistiques et les cotes 1xBet. La Phase 7 combine donc trois sources, chacune
sur son point fort :

| Fournisseur | Rôle | Couverture gratuite | Quota gratuit | Coût |
|---|---|---|---|---|
| **BigBallsData** | Calendrier, résultats et statistiques — **primaire** | Saison en cours, grands championnats et compétitions listées par l'API | ~250 requêtes/jour (jusqu'à 500 avec un compte GitHub) | 0 € |
| **The Odds API** | Cotes **1xBet** (1X2, totals, double chance, BTTS) — **primaire** | Compétitions football actives, pré-match | 500 crédits/mois | 0 € |
| **football-data.org** | Calendrier et résultats — **repli** | 12 compétitions | 10 requêtes/minute | 0 € |
| PulseScore | Non utilisé en Phase 7 — réserve | Cotes 1xBet et résultats | 500 requêtes/mois | 0 € |
| 5DollarFootballAPI | Non utilisé | 5 championnats | 60 requêtes/heure | 0 € |

### Pourquoi cette combinaison

- **BigBallsData** est la seule source gratuite vérifiée qui donne la **saison
  en cours** avec des statistiques de match détaillées (possession, tirs,
  passes, corners, cartons). Les cotes et le xG sont payants : on ne les prend
  donc pas chez lui.
- **The Odds API** est un agrégateur établi, avec des conditions publiées, qui
  référence **1xBet** (`onexbet`) dans la région Europe. Il ne fournit aucune
  statistique : on ne lui demande que des cotes.
- **football-data.org** sert de **repli** quand une compétition n'est pas
  couverte par BigBallsData. Il ne fournit ni cotes ni statistiques.
- **PulseScore** reste une option de secours documentée, non implémentée :
  fournisseur récent, statistiques limitées, quota mensuel faible.
- **5DollarFootballAPI** est écarté : les cotes 1xBet sont réservées à l'offre
  Ultra payante, et sa couverture gratuite recoupe celle de BigBallsData.

### Ce que la combinaison couvre — et ce qui reste manuel

| Donnée | Source | Décision |
|---|---|---|
| 1X2 | The Odds API (`h2h`) | Importée |
| Plus / moins de buts | The Odds API (`totals`) | Importée si les deux issues existent |
| Double chance | The Odds API (`double_chance`, endpoint événement) | Importée si 1xBet la propose |
| Les deux équipes marquent | The Odds API (`btts`, endpoint événement) | Importée si 1xBet la propose |
| Handicap | The Odds API (`spreads`) | **Non importé** en Phase 7 : couverture soccer limitée, coût supplémentaire, inutile aux combinaisons actuelles |
| Score exact | Aucune source retenue | **Reste manuel** |
| xG | BigBallsData | Importé **seulement** si le champ est présent (offre payante) |
| Compositions, blessures | Aucune source gratuite fiable | Hors périmètre |

Aucune cote n'est déduite, extrapolée ou remplacée par un autre bookmaker. Un
marché absent reste absent et saisissable à la main. La double chance n'est
**jamais** calculée à partir des cotes 1X2 : elle n'est importée que si 1xBet
publie réellement le marché.

## Ce que cela change concrètement

- Vous associez une compétition interne à une source, une fois.
- Le calendrier et les résultats se remplissent par aperçu puis validation.
- Les statistiques se complètent par lots, avec le coût exact affiché.
- Les cotes 1xBet se rafraîchissent en un clic, avec le nombre de crédits
  consommés et le solde restant.
- La double chance et le BTTS sont importés quand 1xBet les propose, sans
  déduction à partir d'un autre marché.
- Une correction manuelle est conservée : l'import la signale mais ne l'écrase
  pas.
- Si une source tombe, si un quota est épuisé ou si une cote manque, le reste
  de l'application continue de fonctionner.

## Périmètre

- Football uniquement, comme le moteur actuel.
- Trois connecteurs : `bigballsdata`, `the_odds_api`, `football_data`.
- Découverte des compétitions, association explicite aux compétitions et
  saisons internes.
- Import des rencontres, résultats et statistiques d'équipe.
- Import des marchés 1X2, plus / moins, double chance et BTTS, avec instantanés
  append-only.
- Aperçu obligatoire avant écriture, idempotence, journal des synchronisations.
- Budgets locaux et suivi des quotas réels via les en-têtes des fournisseurs.
- Saisie manuelle conservée pour les données non couvertes et les corrections.

## Hors périmètre (ou jamais)

- Aucun scraping de 1xBet, aucun compte bookmaker, aucun identifiant stocké.
- Aucun placement de pari, aucune recommandation de mise.
- Aucun service payant.
- Aucune synchronisation planifiée automatique : déclenchement manuel. Une
  planification relève de la Phase 8.
- Aucun autre sport, aucune compétition non football.
- Aucun import du score exact ni du handicap : ces marchés restent manuels.
- Aucun service non officiel de scraping : RapidAPI n'est pas utilisé.
- Aucun import de compositions, blessures, suspensions ou arbitres comme
  données structurées.
- Aucune création de rencontre à partir d'une cote : une cote ne s'attache
  qu'à une rencontre déjà existante.
- Aucune fusion automatique d'équipes ambiguës.
- Aucune clé API en base, dans le frontend, dans les journaux ou les sauvegardes.
- Aucune donnée inventée : un champ absent reste nul.

## Décisions techniques

### 1. Architecture : un noyau commun, trois adaptateurs

```
apps/api/app/connectors/
  base.py                 # protocole Connector, types normalisés, erreurs
  http.py                 # client httpx partagé : délais, réessais, rédaction
  quota.py                # budgets locaux et lecture des en-têtes
  matching.py             # normalisation des noms, appariement, suggestions
  bigballsdata/
    client.py             # endpoints, pagination, quota
    mapping.py            # payload -> objets normalisés (pur, sans base)
    importer.py           # écriture, déduplication, conflits
  the_odds_api/
    client.py             # sports, events, odds, crédits
    mapping.py            # h2h / totals / double_chance / btts -> marchés internes
    importer.py           # marchés, sélections, instantanés
  football_data/
    client.py             # compétitions, matchs, throttling
    mapping.py
    importer.py
apps/api/app/services/connectors.py   # orchestration, aperçus, journal
apps/api/app/schemas/connector.py     # schémas d'entrée/sortie
apps/api/app/models/connector.py      # ProviderRef, ConnectorLink, SyncRun, ProviderUsage
apps/api/app/api/v1/connectors.py     # routes
```

- `mapping.py` ne connaît ni SQLAlchemy ni FastAPI : il transforme une charge
  JSON figée en objets normalisés, testables hors réseau.
- Le moteur `apps/api/engine/` reste **inchangé** et sans réseau.
- Chaque client ne voit que sa propre clé.
- `httpx` passe de dépendance de développement à dépendance d'exécution. Aucune
  autre bibliothèque ajoutée.

### 2. BigBallsData — calendrier, résultats, statistiques

| Usage | Endpoint | Coût | Remarque |
|---|---|---|---|
| Lister les compétitions | `GET /v1/leagues?sport=football` | 1 | Résultat mis en cache 24 h |
| Lister les rencontres | `GET /v1/matches?sport=football&league=&season=&limit=100&offset=` | 1 par page | `season` = année de début (ex. `2025`) |
| Statistiques d'une rencontre | `GET /v1/matches/{id}/statistics` | 1 par rencontre | Tous les champs factuels sont gratuits ; `expected_goals` absent sous Solo |
| Lister les équipes | `GET /v1/teams?sport=football&league=` | 1 par page | Pour les suggestions d'appariement |

- Base : `https://api.bigballsdata.com`, HTTPS uniquement.
- Authentification : en-tête `x-api-key`, alimenté **uniquement** par
  `BIGBALLSDATA_KEY`.
- Pagination : `limit=100`, `offset` incrémenté ; arrêt dès qu'une page contient
  moins de 100 éléments. Le nombre de requêtes réellement consommées est
  enregistré dans le journal.
- Le plafond quotidien réel est lu dans `X-RateLimit-Remaining` et
  `X-RateLimit-Reset` ; le budget local s'y ajuste. Réserve de sécurité : 50
  requêtes.
- Limite de débit : un appel toutes les **1,5 seconde** ; aucun parallélisme.
- Un lot de statistiques traite **1 à 10 rencontres**, avec un commit par
  rencontre.
- `season` n'est pas émis dans les objets de liste : la saison est celle du lien
  configuré par l'utilisateur.
- Le statut brut du fournisseur est conservé dans le journal ; la rencontre
  interne reçoit la correspondance ci-dessous.

Correspondance des statuts :

| BigBallsData | Interne | Remarque |
|---|---|---|
| `scheduled` | `programme` | |
| `live`, `in_progress` | `en_cours` | |
| `finished` | `termine` | |
| `postponed` | `reporte` | |
| `cancelled` | `annule` | |
| `suspended` | `en_cours` | Match commencé puis interrompu ; signalé, corrigeable |

Un statut inconnu est traité comme `programme` et **signalé**, jamais deviné.

### 3. The Odds API — cotes 1xBet

| Usage | Endpoint | Coût | Remarque |
|---|---|---|---|
| Lister les sports | `GET /v4/sports` | 0 | Filtre `group = "Soccer"` |
| Lister les événements | `GET /v4/sports/{sport}/events` | 0 | Identifiants, équipes, coup d'envoi |
| Cotes principales | `GET /v4/sports/{sport}/odds?regions=eu&markets=h2h,totals&oddsFormat=decimal` | **2 crédits** | 2 marchés × 1 région, tous les événements de la compétition |
| Marchés étendus | `GET /v4/sports/{sport}/events/{eventId}/odds?regions=eu&markets=double_chance,btts&oddsFormat=decimal` | **1 crédit par marché et par événement** | 2 crédits par rencontre |
| Scores | `GET /v4/sports/{sport}/scores` | 1–2 | **Non utilisé** : BigBallsData fournit les résultats |

- Base : `https://api.the-odds-api.com`, HTTPS uniquement.
- Authentification : paramètre `apiKey`, alimenté **uniquement** par
  `THE_ODDS_API_KEY`. L'URL complète n'est jamais journalisée.
- Les clés de sport sont **découvertes** via `/v4/sports`, jamais codées en dur.
- `regions=eu` est utilisé plutôt qu'un filtre `bookmakers` non garanti par la
  documentation consultée ; la réponse est ensuite filtrée sur
  `bookmakers[].key == "onexbet"`.
- Si 1xBet est absent de la réponse : **aucune substitution**. Le rapport
  indique « 1xBet indisponible pour cette compétition » et zéro cote importée.
- Instantané : `captured_at` = `last_update` du bookmaker, converti en UTC.
- Prix acceptés : décimaux strictement supérieurs à 1,01 et inférieurs à 1 000.
  Hors bornes → ligne ignorée et signalée.
- Les cotes sont stockées **brutes**, sans normalisation de marge.

#### Marchés étendus : double chance et BTTS

L'endpoint principal `/odds` n'accepte que `h2h`, `spreads`, `totals` et
`outrights`. La double chance et le BTTS passent par l'endpoint **par
événement**, qui accepte les marchés supplémentaires.

- Deux marchés demandés par défaut : `double_chance` et `btts`.
- Coût : 2 crédits par rencontre (1 par marché).
- L'aperçu gratuit `/events` sert d'abord à apparier les rencontres ; seules
  les rencontres **à venir dans les 7 jours** et **appariées** sont proposées.
- L'utilisateur sélectionne les rencontres à traiter, **20 au maximum par lot**
  (40 crédits). Le coût exact est affiché avant l'appel.
- Une rencontre dont le marché est absent chez 1xBet est signalée, sans échec
  global et sans substitution.
- Les marchés étendus sont rafraîchis à la demande ; aucun appel automatique.
- Une cote étendue n'est importée que si toutes les issues du marché sont
  présentes (1X, 12, X2 pour la double chance ; Oui et Non pour le BTTS). Une
  ligne incomplète est ignorée et comptée.

### 4. football-data.org — repli calendrier et résultats

| Usage | Endpoint | Coût | Remarque |
|---|---|---|---|
| Lister les compétitions | `GET /v4/competitions` | 1 | Filtre sur les 12 compétitions gratuites |
| Matchs d'une saison | `GET /v4/competitions/{code}/matches?season=` | 1 | Résultats et calendrier |

- Base : `https://api.football-data.org/v4`.
- Authentification : en-tête `X-Auth-Token`, alimenté **uniquement** par
  `FOOTBALL_DATA_KEY`.
- Limite : 10 requêtes/minute. Le client impose **7,5 secondes** entre deux
  appels et lit les en-têtes de quota lorsqu'ils sont présents.
- Utilisé seulement si l'utilisateur choisit explicitement ce connecteur pour
  une compétition, ou si BigBallsData ne la couvre pas.
- Aucune statistique, aucune cote : si une compétition est suivie via
  football-data.org, ses cotes restent manuelles ou proviennent de The Odds API.

### 5. Appariement des compétitions, saisons, équipes et rencontres

- **Compétition** : association explicite dans l'interface. Aucune création
  implicite. Une compétition interne peut être liée à plusieurs fournisseurs.
- **Saison** : le lien stocke le libellé interne et l'identifiant externe
  (`2025` pour BigBallsData et The Odds API, `2025` ou code équivalent pour
  football-data.org).
- **Équipe** : normalisation (minuscules, accents retirés, ponctuation
  neutralisée, suffixes `FC`, `CF`, `SC`, `AFC` ignorés).
  - égalité exacte du nom normalisé ou du code court → association automatique ;
  - aucun candidat → création proposée, jamais imposée ;
  - plusieurs candidats → **aucune fusion** ; l'utilisateur choisit ;
  - suggestions calculées avec `difflib` (bibliothèque standard), jamais
    appliquées automatiquement.
- **Rencontre** : d'abord par référence externe
  `(provider, match, external_id)`, puis par même compétition, mêmes équipes
  normalisées et coup d'envoi à ±30 minutes. Toute ambiguïté est listée.
- Les associations validées sont conservées dans `provider_refs` et réutilisées
  aux synchronisations suivantes.

### 6. Mapping des marchés The Odds API

| Marché API | Marché interne | Règle |
|---|---|---|
| `h2h` | `football.resultat_1x2` | `home` → code `1`, `Draw` → `X`, `away` → `2` |
| `totals` | `football.total_buts` | Grouper par `point` ; `Over` → `plus`, `Under` → `moins` ; les deux issues exigées |
| `double_chance` | `football.double_chance` | `home + Draw` → `1X`, `home + away` → `12`, `Draw + away` → `X2` ; accepter aussi les codes littéraux ; les trois issues exigées |
| `btts` | `football.btts` | `Yes` → `oui`, `No` → `non` ; les deux issues exigées |
| `spreads` | — | Non importé |
| `outrights` | — | Non importé |

- Le marché est retrouvé par sa signature interne
  `(match_id, template_code, période, sujet, ligne)`.
- S'il n'existe pas, il est créé depuis le catalogue
  (`football.resultat_1x2`, `football.total_buts`, `football.double_chance`,
  `football.btts`) avec ses sélections standard.
- S'il existe déjà, il n'est **jamais modifié** : seuls de nouveaux instantanés
  sont ajoutés.
- Une sélection absente du marché existant n'est pas créée à la volée : le
  conflit est signalé.
- Le score exact et le handicap ne sont pas dérivés d'un autre marché. La double
  chance et le BTTS ne sont jamais calculés à partir du 1X2 ou des totals.

### 7. Flux en quatre étapes

#### Étape A — Configuration du lien (0 à 1 requête)

- Choix du fournisseur, de la compétition interne et de la saison.
- Découverte de la compétition externe :
  - BigBallsData : `/v1/leagues?sport=football` (cache 24 h) ;
  - The Odds API : `/v4/sports` (gratuit) ;
  - football-data.org : `/v4/competitions`.
- Le lien est enregistré, désactivable et supprimable sans toucher aux données
  déjà importées.

#### Étape B — Aperçu (coût variable, stocké)

- **Calendrier** : BigBallsData ou football-data.org, une à quelques requêtes
  selon la pagination.
- **Cotes principales** : d'abord `/events` (gratuit) pour vérifier
  l'appariement, puis `/odds` (2 crédits) pour obtenir 1X2 et totals.
- **Marchés étendus** : `/events` (gratuit), sélection de 1 à 20 rencontres,
  puis un appel par rencontre (2 crédits) pour la double chance et le BTTS.
- L'aperçu normalisé est stocké dans `sync_runs` avec le statut `preview` et
  une expiration de **2 heures**.
- Il affiche :
  - le nombre d'éléments reçus ;
  - nouveaux, mises à jour, conflits, ignorés ;
  - équipes à créer ou ambiguës ;
  - marchés réellement disponibles chez 1xBet ;
  - le coût exact et le solde restant.
- **Aucune écriture** dans les tables métier à cette étape.

#### Étape C — Application (0 requête)

- L'application relit l'aperçu stocké et écrit dans une seule transaction.
- Aperçu expiré → `410` ; aperçu déjà appliqué → `409` ; identifiant inconnu →
  `404`.
- Le frontend ne peut pas envoyer de lignes arbitraires : uniquement
  l'identifiant d'aperçu.
- Taille maximale : 1 000 rencontres ou 2 000 cotes par aperçu.

#### Étape D — Statistiques par lots (0 requête d'aperçu, N requêtes d'import)

- L'aperçu liste les rencontres terminées sans statistiques et calcule le coût
  exact, **sans appel réseau**.
- L'application traite **1 à 10 rencontres** par lot, avec 1,5 seconde entre
  deux appels et un commit par rencontre.
- Un lot est refusé si son coût dépasse le budget restant.
- Une rencontre en échec n'annule pas les autres ; elle est signalée et peut
  être relancée.

### 8. Priorité au manuel, idempotence et conflits

- `matches.data_source` et `team_match_stats.data_source` valent `manual`,
  `bigballsdata` ou `football_data`.
- Toute modification manuelle d'une ligne importée la bascule à `manual`.
- Règles :
  1. Une rencontre importée est mise à jour par sa source (score, statut, coup
     d'envoi) tant qu'elle reste importée.
  2. Une rencontre manuelle n'est **jamais** écrasée : la source complète
     seulement ses champs vides et la référence externe. Un désaccord produit un
     **conflit listé** ; la valeur manuelle gagne.
  3. Des statistiques manuelles ne sont jamais remplacées ; le conflit est
     signalé.
  4. Les instantanés de cotes sont **append-only**. Un instantané manuel n'est
     jamais supprimé.
  5. Déduplication d'un instantané importé sur
     `(selection_id, source, captured_at)`. À date égale, la source `manuel`
     est considérée comme prioritaire à l'affichage.
  6. Aucune suppression automatique : une rencontre absente du fournisseur
     reste en base et est signalée.
- Les combinaisons enregistrées en Phase 5 restent **figées** : l'import ne
  modifie ni leurs cotes ni leurs instantanés.
- Réimporter ne crée jamais de doublon : `provider_refs` porte une contrainte
  unique `(provider, entity_type, external_id)`.

### 9. Budgets, quotas et résilience

| Fournisseur | Unité | Limite affichée | Budget local | Réserve |
|---|---|---|---|---|
| BigBallsData | requêtes/jour | ~250 (500 avec GitHub) | 200 | 50 |
| The Odds API | crédits/mois | 500 | 400 | 100 |
| football-data.org | requêtes/minute | 10 | 8 | 2 |

- The Odds API : 2 crédits par rafraîchissement principal de compétition et
  2 crédits par rencontre pour les marchés étendus. Un lot de marchés étendus
  est plafonné à **20 rencontres (40 crédits)**. Le budget mensuel de 400
  crédits permet, par exemple, 4 rafraîchissements principaux par semaine
  (8 crédits) et 40 rencontres étendues par mois (80 crédits), avec une marge
  importante.
- Les compteurs locaux sont persistés dans `provider_usage` et recoupés avec
  les en-têtes réels :
  - BigBallsData : `X-RateLimit-Remaining`, `X-RateLimit-Reset` ;
  - The Odds API : `x-requests-remaining`, `x-requests-used` ;
  - football-data.org : en-têtes de quota lorsque présents.
- Avant un appel payant, le coût est comparé au budget restant. Insuffisant →
  refus explicite avec le nombre disponible.
- Délai de 15 secondes par appel ; deux réessais maximum sur erreur réseau ou
  `5xx` (0,5 s puis 1,5 s) ; **aucun réessai** sur `4xx` ou `429`.
- Erreurs traduites en français :
  - clé absente ou refusée → message explicite, aucun détail secret ;
  - quota épuisé → `429` avec heure de réinitialisation ;
  - compétition ou saison non couverte → `422` ;
  - 1xBet absent → succès partiel à zéro cote, message clair ;
  - réponse illisible → `502` sans écriture partielle.
- Au démarrage de l'API, les synchronisations restées `running` passent à
  `interrompue`. Rien n'est repris automatiquement.

### 10. Sécurité et confidentialité

- Clés lues **exclusivement** dans l'environnement :
  `BIGBALLSDATA_KEY`, `THE_ODDS_API_KEY`, `FOOTBALL_DATA_KEY`.
- L'état exposé se limite à `configured: true/false`. Jamais la clé, jamais un
  fragment, jamais sa longueur.
- Les journaux ne contiennent ni en-tête d'authentification, ni URL complète,
  ni charge utile brute. Un filtre de rédaction masque toute valeur ressemblant
  à une clé.
- Aucune route ne relaie une clé au navigateur ; seul le backend appelle les
  fournisseurs.
- Toutes les routes sont authentifiées ; les écritures exigent le jeton CSRF et
  sont limitées en fréquence.
- Hôtes fixes et HTTPS : aucune URL fournie par l'utilisateur.
- Usage personnel, pas de redistribution. Attribution visible :
  « Données : BigBallsData, The Odds API (cotes 1xBet), football-data.org ».
- `.env.example` contient des valeurs vides, jamais de secret réel.

### 11. Migration additive

Aucune table existante n'est réécrite.

| Ajout | Contenu |
|---|---|
| `provider_refs` | `provider`, `entity_type` (`competition`, `season`, `team`, `match`), `entity_id`, `external_id`, `metadata`, dates. Unique `(provider, entity_type, external_id)` ; index `(entity_type, entity_id, provider)`. |
| `connector_links` | Lien compétition/saison interne ↔ identifiant externe, fournisseur, état, dernières synchronisations. Unique `(provider, external_league_id, external_season)`. |
| `sync_runs` | Journal et aperçus : fournisseur, opération, statut (`preview`, `applied`, `partial`, `failed`, `expired`, `interrompue`), paramètres non secrets, charge utile normalisée, compteurs, requêtes/crédits, quota restant, message assaini, dates, expiration. |
| `provider_usage` | Compteur persistant par fournisseur, période (`day`/`month`) et date de début. Unique `(provider, period_kind, period_start)`. |
| `matches.data_source` | `manual` par défaut, non nul. |
| `matches.source_updated_at` | Date de dernière mise à jour par la source. |
| `team_match_stats.data_source` | `manual` par défaut, non nul. |
| Index `odds_snapshots` | Index non unique `(selection_id, source, captured_at)` pour la déduplication. |

- `provider_refs` est polymorphe : aucune clé étrangère vers `entity_id`,
  l'intégrité est assurée par le service et couverte par des tests.
- Les lignes existantes restent `data_source = manual`.
- `downgrade` supprime les ajouts sans toucher aux données métier.
- Aucun remplissage rétroactif : les données existantes ne sont pas associées
  automatiquement à un identifiant externe.
- Les aperçus expirés depuis plus de 7 jours sont purgés.

## API

| Méthode | Route | Coût | Rôle |
|---|---|---|---|
| `GET` | `/connectors` | 0 | État des trois connecteurs |
| `GET` | `/connectors/links` | 0 | Compétitions suivies |
| `POST` | `/connectors/links` | 0–1 | Créer un lien |
| `PATCH` | `/connectors/links/{id}` | 0 | Activer / désactiver |
| `DELETE` | `/connectors/links/{id}` | 0 | Supprimer le lien, conserver les données |
| `GET` | `/connectors/bigballsdata/leagues?search=` | 0–1 | Recherche de compétition (cache 24 h) |
| `GET` | `/connectors/the-odds-api/sports` | 0 | Sports football disponibles |
| `POST` | `/connectors/links/{id}/fixtures/preview` | 1–N | Aperçu du calendrier |
| `POST` | `/connectors/links/{id}/stats/preview` | 0 | Rencontres à compléter et coût |
| `POST` | `/connectors/links/{id}/stats/apply` | 1–10 | Lot de statistiques |
| `POST` | `/connectors/links/{id}/odds/events` | 0 | Appariement des événements |
| `POST` | `/connectors/links/{id}/odds/preview` | 2 | Aperçu des cotes principales (1X2, totals) |
| `POST` | `/connectors/links/{id}/odds/extended/preview` | 2 × N (max. 40) | Aperçu double chance + BTTS pour N rencontres |
| `POST` | `/connectors/sync-runs/{id}/apply` | 0 | Appliquer un aperçu |
| `POST` | `/connectors/the-odds-api/events/{eventId}/link` | 0 | Associer un événement à une rencontre |
| `GET` | `/connectors/sync-runs?limit=20` | 0 | Journal |
| `GET` | `/connectors/provider-usage` | 0 | Quotas locaux et réels |

Exemple d'aperçu de cotes :

```json
{
  "run_id": "7c1e…",
  "provider": "the_odds_api",
  "operation": "odds",
  "link": {
    "competition": "Ligue 1",
    "season": "2025-2026",
    "sport_key": "soccer_france_ligue_one"
  },
  "expires_at": "2026-11-09T18:00:00Z",
  "quota": { "credits_used": 2, "credits_remaining": 398 },
  "counts": {
    "events_received": 9,
    "events_matched": 8,
    "events_unmatched": 1,
    "markets_1x2": 8,
    "markets_totals": 6,
    "odds_ready": 42,
    "ignored": 1
  },
  "bookmaker": "1xBet",
  "unmatched": [
    { "event_id": "abc123", "label": "Nice — Lens", "kickoff_utc": "2026-11-15T16:00:00Z" }
  ],
  "avertissement": "Cotes agrégées via The Odds API. Aucune cote inventée, aucune substitution de bookmaker."
}
```

Exemple d'aperçu de marchés étendus :

```json
{
  "run_id": "9d2a…",
  "provider": "the_odds_api",
  "operation": "odds_extended",
  "markets": ["double_chance", "btts"],
  "expires_at": "2026-11-09T18:00:00Z",
  "quota": { "credits_used": 40, "credits_remaining": 360 },
  "counts": {
    "events_requested": 20,
    "events_with_double_chance": 17,
    "events_with_btts": 15,
    "odds_ready": 96,
    "ignored": 4
  },
  "bookmaker": "1xBet",
  "avertissement": "Les marchés absents chez 1xBet restent manuels. Aucune déduction."
}
```

Erreurs au format RFC 7807, en français, sans secret.

## Interface

Nouvelle page **Connecteurs** dans la navigation latérale :

1. **Cartes d'état** : clé configurée, quota restant, dernière synchronisation,
   lien vers la documentation officielle. Aucun champ de saisie de clé.
2. **Compétitions suivies** : fournisseur, compétition, saison, état, dernière
   synchronisation, bouton désactiver.
3. **Assistant de lien** : fournisseur → compétition externe → compétition et
   saison internes → activation.
4. **Calendrier** : aperçu (compteurs, conflits, équipes ambiguës, coût) puis
   application.
5. **Statistiques** : rencontres manquantes, coût exact, lot de 1 à 10,
   résultat par rencontre.
6. **Cotes principales** : appariement gratuit des événements, aperçu payant
   (2 crédits affichés), application, événements non appariés avec association
   manuelle.
7. **Marchés étendus** : liste des rencontres à venir (7 jours), sélection de
   1 à 20 rencontres, coût affiché (2 crédits par rencontre), aperçu indiquant
   si 1xBet propose réellement la double chance et le BTTS.
8. **Journal** : statuts, compteurs, requêtes/crédits, erreurs ; relance d'un
   aperçu expiré.
9. **Bandeau permanent** : « Cotes 1xBet agrégées via The Odds API. Aucune cote
   inventée. Les marchés non fournis restent manuels. »

- Responsive, thème sombre, composants existants, aucune nouvelle bibliothèque
  graphique.
- Aucune formulation certaine, aucun conseil de pari, aucune promesse de gain.
- Les erreurs de quota, de couverture ou de clé sont affichées en français avec
  l'action attendue.
- Si une clé manque, la page reste utilisable et indique comment renseigner
  `.env` puis redémarrer l'API.

## Risques et parades

| Risque | Parade |
|---|---|
| Quota BigBallsData épuisé | Budget 200/jour, réserve 50, coût affiché, lots de 10, refus avant dépassement |
| Crédits The Odds API épuisés | Budget 400/mois, aperçu gratuit avant l'appel payant, coût affiché (2 crédits par compétition, 2 par rencontre étendue), lot plafonné à 40 crédits |
| Limite football-data.org | 7,5 s entre appels, budget 8/minute, aucun réessai sur `429` |
| 1xBet absent d'une compétition | Zéro cote importée, message explicite, aucune substitution |
| 1xBet sans double chance ou BTTS | Marché signalé absent, aucune déduction depuis le 1X2 ou les totals |
| Marché `totals` incomplet | Seules les lignes avec `Over` et `Under` sont importées |
| Marché `double_chance` incomplet | Les trois issues `1X`, `12`, `X2` sont exigées |
| Marché `btts` incomplet | Les deux issues `Oui` et `Non` sont exigées |
| Couverture incomplète de BigBallsData | Repli football-data.org, saisie manuelle possible |
| Panne ou changement de format | Validation stricte, `502` sans écriture partielle, tests sur charges figées |
| Doublons après réimport | Références externes uniques, déduplication des instantanés, tests dédiés |
| Écrasement d'une saisie manuelle | `data_source`, priorité manuelle, conflits listés, tests |
| Fusion erronée de deux équipes | Égalité stricte seulement, ambiguïté → choix manuel, jamais de fusion auto |
| Cote rattachée à la mauvaise rencontre | Appariement par référence, puis noms + coup d'envoi ±30 min, ambiguïté refusée |
| Cote inventée ou extrapolée | Mapping limité à `h2h`, `totals`, `double_chance` et `btts`, aucune dérivation, test dédié |
| Statistiques absentes ou partielles | Aucune valeur inventée, couverture affichée |
| Fuite de clé | Environnement uniquement, rédaction des journaux, tests sur réponses et logs |
| Import perçu comme une garantie | Textes sur l'incertitude inchangés, avertissement permanent |
| Modification des combinaisons enregistrées | Aucune écriture dans les instantanés de la Phase 5 |
| Fuseaux horaires | Conversion systématique en UTC |
| Redémarrage pendant un import | Statut `interrompue`, reprise manuelle, aucun état inventé |
| Service non officiel / scraping | Aucune source non officielle : The Odds API est un agrégateur établi, sans scraping direct de 1xBet |

## Tests prévus

### Mapping (fonctions pures, charges JSON figées)
- BigBallsData : rencontre complète, incomplète, statut inconnu, date UTC,
  pagination, score nul, `suspended`.
- The Odds API : `h2h` complet, `Draw`, `totals` avec plusieurs lignes, ligne
  incomplète, bookmaker absent, prix hors bornes, `last_update` invalide.
- Double chance : trois issues nommées par équipes, codes littéraux, issue
  manquante, issue dupliquée, noms inversés.
- BTTS : `Yes`/`No`, `Oui`/`Non`, issue manquante, valeur inattendue.
- Marchés étendus : une rencontre sans marché chez 1xBet ne produit aucune cote.
- football-data.org : match programmé, terminé, reporté, score absent.
- Normalisation des noms : accents, suffixes, collisions, suggestions.
- Aucune lecture d'un champ de cote BigBallsData ; aucune lecture d'un champ de
  statistique The Odds API.
- Aucune valeur inventée quand un champ est absent.

### Clients HTTP (transport simulé, aucun réseau)
- En-têtes d'authentification corrects, jamais journalisés.
- Traduction des erreurs 401, 403, 422, 429, 500 et réponse illisible.
- Réessais uniquement sur réseau et `5xx`, jamais sur `4xx`.
- Espacement de 1,5 s (BigBallsData) et 7,5 s (football-data.org).
- Quotas : refus d'un appel trop coûteux, comptage exact, réinitialisation
  journalière/mensuelle UTC, lecture des en-têtes.
- Absence de 1xBet → zéro cote, message dédié.
- Marchés étendus : un appel par rencontre, coût exact, lot de 20 maximum,
  refus si le budget restant est insuffisant.

### Import et base (SQLite)
- Aperçu sans écriture métier ; application sans requête réseau.
- Réimport : aucun doublon, compteurs `updates` corrects.
- Aperçu expiré → `410` ; double application → `409` ; identifiant inconnu →
  `404`.
- Rencontre manuelle : champs vides complétés, valeurs non vides conservées,
  conflit listé.
- Statistiques manuelles jamais écrasées.
- Équipes ambiguës non fusionnées ; création désactivée → rencontre ignorée et
  comptée.
- Cotes : marché créé une seule fois, sélections standard, instantané dédupliqué
  sur `(selection_id, source, captured_at)`, instantané manuel conservé.
- Double chance et BTTS : marché `football.double_chance` / `football.btts`
  réutilisé s'il existe, sinon créé avec les codes `1X`/`12`/`X2` et
  `oui`/`non`.
- Marché incomplet : aucune ligne partielle n'est écrite.
- Une rencontre inconnue ne reçoit jamais de cote.
- Tables `markets`, `selections` et `odds_snapshots` inchangées par un import de
  calendrier ou de statistiques.
- Combinaisons enregistrées inchangées.
- Journal : statuts, compteurs, durée, quotas, aucune clé.
- Migration : `upgrade` puis `downgrade` sur base vierge, données existantes
  marquées `manual`.

### API
- Authentification obligatoire ; CSRF sur chaque écriture.
- Clé absente → réponse explicite, page fonctionnelle, aucun `500`.
- Aperçu et application cohérents ; refus des charges arbitraires.
- Limite de fréquence et messages d'erreur en français.
- Aucune réponse ne contient une clé ni un fragment.

### Interface
- Page Connecteurs : état sans clé, création de lien, aperçu, application,
  lots, cotes, journal, erreurs de quota.
- Bandeau « cotes agrégées, aucune cote inventée » visible.
- Responsive, navigation, absence d'erreur console.
- Aucune formulation certaine.

## Critères d'acceptation

1. Les trois clés sont lues uniquement depuis l'environnement et n'apparaissent
   ni en base, ni dans le frontend, ni dans les journaux, ni dans les réponses.
2. Une compétition peut être associée explicitement à une source et à une
   saison interne.
3. Le calendrier est prévisualisé avec compteurs et conflits avant toute
   écriture.
4. L'application d'un aperçu n'effectue aucune requête supplémentaire et ne crée
   aucun doublon en cas de réimport.
5. Les statistiques sont importées par lots dont le coût exact est affiché et le
   budget quotidien respecté.
6. Les cotes 1xBet sont importées avec `bookmaker = "1xBet"`,
   `source = "the_odds_api"` et un instantané horodaté.
7. `h2h`, `totals`, `double_chance` et `btts` sont les seuls marchés importés ;
   aucun autre marché n'est dérivé.
8. Une cote n'est jamais créée pour une rencontre inconnue ni remplacée par un
   autre bookmaker.
9. La double chance et le BTTS ne sont écrits que si 1xBet publie toutes leurs
   issues ; sinon le marché reste absent et manuel.
10. Une donnée manuelle n'est jamais écrasée ; les conflits sont listés.
11. Les quotas locaux et réels sont consultables ; un dépassement est refusé
    avant l'appel, y compris pour les marchés étendus.
12. Les combinaisons enregistrées restent lisibles et inchangées.
13. Une clé absente, un quota épuisé, une compétition non couverte ou un
    bookmaker absent produisent un message clair, jamais une erreur non
    maîtrisée.
14. `ruff`, `mypy`, `pytest`, `eslint`, `tsc` et `next build` passent.
15. La documentation est à jour : `README.md`, `docs/exploitation/api.md`,
    `docs/exploitation/environnement.md` et `.env.example`.

## Livrables

- `apps/api/app/connectors/` : noyau, trois adaptateurs, mapping pur, clients,
  importateurs.
- `apps/api/app/models/connector.py` : `ProviderRef`, `ConnectorLink`,
  `SyncRun`, `ProviderUsage`.
- `apps/api/app/services/connectors.py` : orchestration, aperçus, quotas,
  journal.
- `apps/api/app/schemas/connector.py` : schémas d'entrée et de sortie.
- `apps/api/app/api/v1/connectors.py` : routes et dépendances.
- Ajouts `data_source` et index sur les modèles existants, migration Alembic
  additive.
- `apps/api/app/core/config.py` : trois clés facultatives, budgets et délais.
- `apps/web/src/app/(app)/connecteurs/page.tsx` : page complète.
- `apps/web/src/components/` : cartes d'état, assistant de lien, aperçu,
  conflits, lots, cotes, journal.
- `apps/web/src/components/app-shell.tsx` : entrée « Connecteurs ».
- Tests mapping, clients simulés, import SQLite, API et interface.
- Documentation d'exploitation et `.env.example`.

## Points soumis à validation

1. **Combinaison** : BigBallsData (calendrier, résultats, statistiques) +
   The Odds API (cotes 1xBet) + football-data.org (repli).
2. **Budgets** : 200 requêtes/jour BigBallsData, 400 crédits/mois The Odds API,
   8 requêtes/minute football-data.org.
3. **Cotes importées** : 1X2, plus / moins, double chance et BTTS ; score exact
   et handicap restent manuels.
4. **Marchés étendus** : 2 crédits par rencontre, lot de 20 rencontres maximum,
   uniquement si 1xBet publie toutes les issues.
5. **Aucune substitution** : si 1xBet est absent, aucune cote n'est importée.
6. **Priorité au manuel** : une correction manuelle n'est jamais écrasée.
7. **Pas de planification automatique** en Phase 7 : chaque import est
   déclenché et confirmé.
8. **PulseScore et 5DollarFootballAPI** ne sont pas implémentés.
9. **RapidAPI n'est pas utilisé** : les marchés supplémentaires passent par
   The Odds API, ce qui évite un service non officiel.

Après validation, l'implémentation suivra cet ordre : migration et modèles,
noyau `http`/`quota`/`matching` testé hors réseau, adaptateur BigBallsData,
adaptateur The Odds API, adaptateur football-data.org, services et routes API,
page Connecteurs, puis vérifications complètes et documentation.

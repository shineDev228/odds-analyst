# Phase 7 — Connecteurs de données

> **Statut : plan proposé — en attente de validation.** Connexion à
> **API-Football** (offre gratuite) pour importer calendrier, résultats et
> statistiques d'équipe, sans jamais importer de cotes.

## Objectif

Réduire la saisie manuelle et élargir l'historique du moteur statistique en
connectant l'application à une source de données sportives **gratuite et
autorisée** :

1. **Calendrier et résultats** : importer les rencontres d'une compétition et
   d'une saison, avec leur statut, leur score et leur coup d'envoi.
2. **Statistiques d'équipe** : importer tirs, tirs cadrés, possession, corners,
   cartons et, lorsque le fournisseur les expose, les buts attendus (xG).
3. **Traçabilité** : savoir quelles données viennent de l'API, lesquelles sont
   manuelles, et ne jamais écraser une saisie manuelle par une importation.
4. **Sobriété** : respecter le quota de l'offre gratuite (100 requêtes/jour) et
   ne jamais dépenser de requête sans que l'utilisateur l'ait confirmé.

L'import améliore la **couverture** et le **volume** des données. Il ne rend pas
le modèle plus certain, ne garantit aucun résultat et ne constitue pas un
conseil de pari.

## Périmètre

- Fournisseur unique : **API-Football** (API-Sports), offre gratuite.
- Football uniquement, comme le moteur actuel.
- Endpoints utilisés : recherche de compétition, calendrier, statistiques de
  rencontre. **Aucun endpoint de cotes.**
- Import contrôlé des compétitions, saisons, équipes, rencontres et
  statistiques d'équipe.
- Prévisualisation obligatoire avant toute écriture.
- Déduplication et idempotence : réimporter ne crée jamais de doublon.
- Journal local des synchronisations et suivi du quota.
- Priorité absolue aux données saisies manuellement.

## Hors périmètre (ou jamais)

- **Aucune cote, aucun marché, aucune sélection, aucun bookmaker** importé :
  les cotes 1xBet restent saisies manuellement.
- Aucun scraping de 1xBet, aucun contournement des limites de l'API.
- Aucune composition, blessure ou suspension : l'offre gratuite ne les fournit
  pas de façon fiable.
- Aucun autre sport.
- Aucune synchronisation planifiée automatique : déclenchement manuel. Une
  planification éventuelle relève de la Phase 8.
- Aucun stockage de la clé API en base, dans le frontend, dans les journaux ou
  dans les sauvegardes.
- Aucun service payant, aucun apprentissage automatique, aucun placement de
  pari.

## Ce que cela change concrètement

- Vous choisissez une compétition et une saison, puis vous voyez **ce qui sera
  importé avant validation**.
- Les rencontres et leurs résultats se remplissent sans recopie.
- Les statistiques se complètent par petits lots, avec le coût en requêtes
  affiché avant chaque lot.
- Tout ce que vous avez saisi à la main reste prioritaire : l'import ne peut
  pas le modifier silencieusement.

## Décisions techniques

### 1. Fournisseur, endpoints et quota

| Usage | Endpoint | Coût | Remarque |
|---|---|---|---|
| Rechercher une compétition | `GET /leagues?search=` | 1 requête | Résultat mis en cache 24 h en mémoire |
| Calendrier d'une saison | `GET /fixtures?league=&season=` | 1 requête | Retourne tous les matchs de la saison |
| Statistiques d'une rencontre | `GET /fixtures/statistics?fixture=` | 1 requête | **Une requête par rencontre** |
| Santé de la clé | aucun appel dédié | 0 | L'état est déduit du dernier appel |

- Base fixe : `https://v3.football.api-sports.io`, en HTTPS uniquement.
- En-tête d'authentification : `x-apisports-key`, alimenté **uniquement** par
  la variable d'environnement `API_FOOTBALL_KEY`.
- L'offre gratuite annonce **100 requêtes/jour** et une limite de débit de
  l'ordre de **10 requêtes/minute**. Les deux limites sont traitées :
  - budget quotidien local fixé à **90 requêtes** (10 gardées en réserve) ;
  - espacement de **6,5 secondes** entre deux appels de statistiques.
- Les saisons accessibles sur l'offre gratuite **ne sont pas codées en dur** :
  elles sont lues dans la réponse et une erreur de plan est traduite par un
  message clair, sans boucle de réessai.
- Les réponses sont validées avant usage. Toute valeur absente ou non numérique
  est ignorée, jamais inventée.
- Les cotes éventuellement présentes dans une réponse ne sont **jamais lues ni
  enregistrées**.

### 2. Architecture : client isolé, mapping pur, importateur transactionnel

```
apps/api/app/connectors/api_football/
  client.py      # HTTP, clé, quota, délais, erreurs — seul module qui voit la clé
  mapping.py     # fonctions pures : payload API -> objets normalisés (sans base)
  importer.py    # écriture en base, déduplication, conflits
  errors.py      # erreurs métier traduites en messages français
apps/api/app/services/connectors.py   # orchestration, aperçus, journal
apps/api/app/schemas/connector.py     # schémas d'entrée/sortie
```

- Le moteur `apps/api/engine/` reste **inchangé** et sans réseau.
- `mapping.py` ne connaît ni SQLAlchemy ni FastAPI ; il est testable sur des
  charges JSON figées.
- La clé ne sort jamais de `client.py` : les objets normalisés, les journaux et
  les réponses API n'en contiennent aucune trace.
- Aucune nouvelle bibliothèque : `httpx` est déjà présent en dépendance de
  développement ; il passe en dépendance d'exécution.

### 3. Flux en quatre étapes, avec confirmation

#### Étape A — Découverte de la compétition (0 ou 1 requête)

- Recherche par nom via `/leagues?search=`, mise en cache mémoire 24 h.
- L'utilisateur choisit une ligue API, une saison et la compétition interne à
  associer (existante ou à créer). Aucune création implicite.

#### Étape B — Aperçu du calendrier (1 requête)

- Appel unique `/fixtures?league=&season=`.
- Les données normalisées sont stockées dans le journal de synchronisation
  (statut `preview`, expiration **2 heures**).
- L'aperçu affiche :
  - nombre de rencontres reçues ;
  - rencontres nouvelles, à mettre à jour, en conflit, ignorées ;
  - équipes à créer ou à associer manuellement ;
  - requêtes estimées et quota restant.
- **Aucune écriture** dans les tables métier à cette étape.

#### Étape C — Application du calendrier (0 requête)

- L'application relit **l'aperçu stocké**, le valide et écrit dans une seule
  transaction.
- Un aperçu expiré renvoie `410` ; un aperçu déjà appliqué renvoie `409`.
- Le frontend ne peut pas envoyer des lignes arbitraires : il référence
  uniquement l'identifiant d'aperçu.
- Taille maximale : 1 000 rencontres par aperçu ; au-delà, l'import est refusé
  avec un message explicite.

#### Étape D — Statistiques par lots (0 requête d'aperçu, N requêtes d'import)

- L'aperçu des statistiques ne consomme **aucune requête** : il liste les
  rencontres terminées sans statistiques et calcule le coût exact.
- L'application traite **1 à 10 rencontres par lot** (10 par défaut), avec
  6,5 secondes entre deux appels et un commit par rencontre.
- Un lot est refusé si son coût dépasse le budget restant.
- Le résultat détaille, pour chaque rencontre : importée, ignorée ou en échec.
- Une rencontre en échec n'annule pas les autres ; elle est signalée et pourra
  être relancée.

### 4. Mapping des données

#### Compétition et saison

- `league.id` → `competitions.external_id` (provider `api_football`).
- Nom = `league.name`, pays = `league.country`, sport = football, tier inconnu
  (`null`).
- Saison : `external_id = "<league_id>:<year>"` pour rester unique entre
  compétitions.
- Libellé de saison déduit des dates : si la saison commence en juillet ou
  après, `2024-2025` ; sinon `2024`.
- Dates de début et de fin reprises de l'API lorsqu'elles existent, sinon
  déduites de la première et de la dernière rencontre.
- Une saison existante avec le même libellé est réutilisée ; aucun doublon.

#### Équipe

- Correspondance par nom normalisé (minuscules, accents retirés, ponctuation et
  suffixes courants neutralisés) **dans le même sport**.
- Un seul candidat → association automatique.
- Aucun candidat → création si l'option « créer les équipes manquantes » est
  cochée, sinon la rencontre est ignorée et signalée.
- Plusieurs candidats → **aucune fusion automatique** : l'utilisateur doit
  choisir l'équipe existante.
- `short_name` = code API s'il tient en 40 caractères, sinon `null`.
- Pays = pays de la compétition (l'API ne fournit pas le pays d'équipe dans le
  calendrier).

#### Rencontre

| Champ API | Champ interne | Règle |
|---|---|---|
| `fixture.id` | `external_id` | Clé d'idempotence |
| `fixture.date` | `kickoff_at` | Converti en UTC |
| `fixture.status.short` | `status` | Table de correspondance ci-dessous |
| `fixture.venue.name` | `venue` | Tronqué à 120 caractères |
| `fixture.referee` | `referee` | Tronqué à 120 caractères |
| `goals.home/away` | `home_score/away_score` | Entiers positifs ou nuls |
| `score.halftime.*` | `half_time_*_score` | Si présent |
| `teams.home/away` | `home_team_id/away_team_id` | Mapping équipes |

Correspondance des statuts :

| API | Interne |
|---|---|
| `NS`, `TBD` | `programme` |
| `1H`, `HT`, `2H`, `ET`, `BT`, `P`, `SUSP`, `INT` | `en_cours` |
| `FT`, `AET`, `PEN` | `termine` |
| `PST` | `reporte` |
| `CANC`, `ABD`, `AWD`, `WO` | `annule` |

- Un statut inconnu est traité comme `programme` et signalé, jamais deviné.

#### Statistiques d'équipe

| Type API | Champ interne | Conversion |
|---|---|---|
| `Total Shots` | `shots` | Entier |
| `Shots on Goal` | `shots_on_target` | Entier |
| `Ball Possession` | `possession` | `"54%"` → `54.0`, borné 0–100 |
| `Corner Kicks` | `corners` | Entier |
| `Yellow Cards` | `yellow_cards` | Entier |
| `Red Cards` | `red_cards` | Entier |
| `expected_goals` | `expected_goals` | Décimal, borné 0–20 |

- `goals_for` / `goals_against` sont déduits du score final, pas des
  statistiques.
- Les autres types sont ignorés.
- Une valeur négative ou hors bornes est ignorée et signalée ; elle n'est pas
  corrigée arbitrairement.
- Si aucune statistique exploitable n'est fournie, aucune ligne n'est créée :
  la rencontre reste « sans statistiques » et le moteur utilise les buts.

### 5. Idempotence, priorité au manuel et conflits

- Contrainte unique `(external_provider, external_id)` sur compétitions,
  saisons, équipes et rencontres.
- Contrainte existante `(match_id, team_id)` conservée pour les statistiques.
- Chaque rencontre et chaque ligne de statistiques porte une origine :
  `data_source = manual | api_football`.
- Toute modification manuelle d'une ligne importée bascule son origine à
  `manual` : elle devient prioritaire.
- Règles de conflit :
  1. Une rencontre importée est mise à jour par l'API (score, statut, coup
     d'envoi, lieu, arbitre) sauf ses notes.
  2. Une rencontre manuelle n'est **jamais** écrasée. Si une rencontre
     correspondante existe (même saison, mêmes équipes, coup d'envoi à
     ±15 minutes), elle est seulement liée à l'identifiant externe et ses
     champs vides sont complétés.
  3. Un désaccord de score ou de statut sur une rencontre manuelle produit un
     **conflit listé** : la valeur manuelle gagne.
  4. Des statistiques manuelles ne sont jamais remplacées ; le conflit est
     signalé.
  5. Aucune suppression automatique : une rencontre absente de l'API reste en
     base et est signalée.
- Les combinaisons enregistrées en Phase 5 restent **figées** : l'import ne
  modifie ni leurs cotes ni leurs instantanés.

### 6. Quota, délais et résilience

- Budget quotidien local : **90 requêtes** par jour UTC, réserve de 10.
- Le total du jour est la somme des `requests_used` du journal, recoupée avec
  l'en-tête `x-ratelimit-requests-remaining` du dernier appel.
- Avant un lot, le coût est comparé au budget restant ; si insuffisant, le lot
  est refusé en indiquant le nombre disponible.
- Délai de 15 secondes par appel, deux réessais maximum sur erreur réseau ou
  `5xx` (0,5 s puis 1,5 s), **aucun réessai** sur `4xx` ou `429`.
- Traduction des erreurs :
  - clé absente ou refusée → message explicite, aucun détail secret ;
  - quota épuisé → `429` avec heure de réinitialisation estimée ;
  - saison non incluse dans l'offre gratuite → `422` explicite ;
  - réponse illisible → `502` sans écriture partielle.
- Au démarrage de l'API, les synchronisations restées `running` sont marquées
  `interrompue`. Rien n'est repris automatiquement.

### 7. Sécurité et confidentialité

- Clé lue **exclusivement** depuis l'environnement (`API_FOOTBALL_KEY`).
- L'état exposé se limite à `configured: true/false` : jamais la clé, jamais
  un fragment, jamais sa longueur.
- Les journaux ne contiennent ni en-têtes, ni URL complète, ni charge utile.
  Un filtre de rédaction masque toute valeur ressemblant à une clé.
- Aucune route ne relaie la clé au navigateur ; seul le backend appelle l'API.
- Toutes les routes sont authentifiées ; les routes d'écriture exigent le jeton
  CSRF et sont limitées en fréquence.
- Hôte fixe et HTTPS : pas d'URL fournie par l'utilisateur, donc pas de risque
  de requête vers un hôte arbitraire.
- Usage personnel, pas de redistribution des données, attribution
  « Données : API-Football » dans la page Connecteurs et la documentation.
- `API_FOOTBALL_KEY` reste vide dans `.env.example` et n'est jamais commitée.

### 8. Migration additive

Aucune table existante n'est réécrite ; seules des colonnes nullables et deux
tables nouvelles sont ajoutées.

| Table | Ajout |
|---|---|
| `competitions` | `external_provider`, `external_id`, index et unicité partielle |
| `seasons` | `external_provider`, `external_id`, index et unicité partielle |
| `teams` | `external_provider`, `external_id`, index et unicité partielle |
| `matches` | `external_provider`, `external_id`, `data_source`, index et unicité partielle |
| `team_match_stats` | `data_source` |
| `sync_runs` | nouvelle table de journal et d'aperçu |

`sync_runs` contient : identifiant, fournisseur, type d'opération, statut
(`preview`, `applied`, `partial`, `failed`, `expired`, `interrompue`),
paramètres non secrets, charge utile normalisée de l'aperçu, compteurs,
nombre de requêtes, quota restant, message d'erreur assaini, dates et
expiration. Les lignes expirées sont purgées au-delà de 7 jours.

- Les lignes existantes restent `data_source = manual`.
- La migration est réversible : `downgrade` supprime les ajouts sans toucher
  aux données métier.
- Aucun remplissage rétroactif : les données existantes ne sont pas associées
  automatiquement à un identifiant externe.

## API

| Méthode | Route | Coût | Rôle |
|---|---|---|---|
| `GET` | `/connectors` | 0 | État des connecteurs |
| `GET` | `/connectors/api-football/status` | 0 | Clé configurée, quota, dernière synchronisation |
| `GET` | `/connectors/api-football/leagues?search=` | 0–1 | Recherche de compétition (cache 24 h) |
| `POST` | `/connectors/api-football/fixtures/preview` | 1 | Aperçu du calendrier et des conflits |
| `POST` | `/connectors/api-football/fixtures/apply` | 0 | Application de l'aperçu stocké |
| `POST` | `/connectors/api-football/stats/preview` | 0 | Rencontres à compléter et coût exact |
| `POST` | `/connectors/api-football/stats/apply` | 1–10 | Import d'un lot de statistiques |
| `GET` | `/connectors/sync-runs?limit=20` | 0 | Journal des synchronisations |

Exemple d'aperçu :

```json
{
  "run_id": "3f0c…",
  "provider": "api_football",
  "league": { "external_id": "61", "name": "Ligue 1", "country": "France" },
  "season": { "external_id": "61:2025", "label": "2025-2026" },
  "expires_at": "2026-11-09T18:00:00Z",
  "quota": { "used_today": 12, "remaining": 78 },
  "counts": {
    "fixtures": 306,
    "new": 281,
    "updates": 20,
    "conflicts": 5,
    "ignored": 0,
    "teams_to_create": 4,
    "teams_ambiguous": 1
  },
  "conflicts": [
    {
      "kind": "match",
      "label": "Paris SG — Marseille",
      "field": "home_score",
      "manual": 2,
      "provider": 1
    }
  ],
  "avertissement": "Aucune cote n'est importée. Les données manuelles restent prioritaires."
}
```

Erreurs au format RFC 7807, en français, sans secret. Exemple de conflit
d'application : `409` avec la liste des aperçus déjà appliqués.

## Interface

Nouvelle page **Connecteurs** dans la navigation latérale :

1. **Carte d'état** : clé configurée ou non, quota restant, dernière
   synchronisation, lien vers la documentation officielle du fournisseur.
2. **Étape 1 — Compétition** : recherche, choix de la ligue et de la saison,
   association à une compétition interne existante ou création explicite.
3. **Étape 2 — Aperçu** : compteurs, conflits, équipes à créer ou ambiguës,
   coût en requêtes, bouton de confirmation.
4. **Étape 3 — Application** : résultat détaillé, aucune requête supplémentaire.
5. **Étape 4 — Statistiques** : liste des rencontres à compléter, coût exact,
   choix du lot (1 à 10), résultat par rencontre.
6. **Journal** : historique des synchronisations, statuts, compteurs, requêtes
   consommées ; possibilité de relancer un aperçu expiré.
7. **Bandeau permanent** : « Aucune cote n'est importée. Les données manuelles
   restent prioritaires. »
8. **État vide / clé absente** : procédure claire pour renseigner
   `API_FOOTBALL_KEY` dans `.env` puis redémarrer l'API, sans jamais demander la
   clé dans l'interface.

- Responsive, thème sombre, composants existants, aucune nouvelle bibliothèque
  graphique.
- Aucune formulation certaine, aucun conseil de pari, aucune promesse de gain.
- Les erreurs de quota ou de plan sont affichées en français, avec l'action
  attendue.

## Risques et parades

| Risque | Parade |
|---|---|
| Quota de 100 requêtes/jour épuisé | Budget local 90, aperçu du coût, lots de 10, refus avant dépassement |
| Limite de 10 requêtes/minute | Espacement de 6,5 s, aucun réessai sur `429` |
| Saison non incluse dans l'offre gratuite | Message explicite, pas de boucle, saisons lues dans l'API |
| Panne ou changement de format du fournisseur | Validation stricte, `502` sans écriture partielle, transaction par aperçu |
| Doublons après réimport | Identifiants externes uniques, tests de réimport |
| Écrasement d'une saisie manuelle | `data_source`, priorité manuelle, conflits listés, tests dédiés |
| Fusion erronée de deux équipes | Correspondance normalisée stricte, ambiguïté → choix manuel, jamais de fusion auto |
| Statistiques absentes ou partielles | Aucune valeur inventée, couverture xG inchangée et affichée |
| Import de cotes par erreur | Endpoints limités, aucun champ de cote lu, test interdisant l'accès aux tables de marchés |
| Fuite de la clé | Environnement uniquement, rédaction des journaux, tests sur les réponses et logs |
| Import perçu comme une garantie | Textes inchangés sur l'incertitude, avertissement permanent |
| Modification des combinaisons enregistrées | Aucune écriture dans les instantanés de la Phase 5 |
| Fuseaux horaires | Conversion systématique en UTC, comme les phases précédentes |
| Lot trop long ou blocage | 10 rencontres maximum, délai de 15 s, timeout client explicite |
| Redémarrage pendant un import | Statut `interrompue`, reprise manuelle, aucun état inventé |

## Tests prévus

### Mapping (fonctions pures)
- Fixture complète, incomplète, statut inconnu, date avec fuseau.
- Saison à cheval sur deux années et saison calendaire.
- Normalisation des noms d'équipes, accents, suffixes et collisions.
- Statistiques : `"54%"`, entiers, champs absents, valeurs hors bornes.
- Absence de xG : aucune valeur inventée.
- Aucune lecture d'un éventuel champ de cote.

### Client HTTP (transport simulé, aucun réseau)
- En-tête d'authentification correct, jamais journalisé.
- Traduction des erreurs 401, 403, 422, 429, 500 et réponse illisible.
- Réessais uniquement sur réseau et `5xx`, jamais sur `4xx`.
- Délai de 6,5 s respecté dans un lot simulé.
- Quota : refus d'un lot trop coûteux, comptage exact, réinitialisation UTC.

### Import et base (SQLite)
- Aperçu sans écriture métier, application sans requête réseau.
- Réimport : aucun doublon, compteurs `updates` corrects.
- Aperçu expiré → `410` ; double application → `409` ; identifiant inconnu →
  `404`.
- Rencontre manuelle : champs vides complétés, valeurs non vides conservées,
  conflit listé.
- Statistiques manuelles jamais écrasées.
- Équipes ambiguës non fusionnées ; option de création désactivée → rencontre
  ignorée et comptée.
- Tables `markets`, `selections` et `selection_odds` inchangées après import.
- Combinaisons enregistrées inchangées.
- Journal : statuts, compteurs, durée, quota, aucune clé.
- Migration : `upgrade` puis `downgrade` sur une base vierge.

### API
- Authentification obligatoire ; CSRF sur chaque `POST`.
- Clé absente → réponse explicite, page fonctionnelle, aucun `500`.
- Aperçu et application cohérents ; refus des charges arbitraires.
- Limite de fréquence et messages d'erreur en français.
- Aucune réponse ne contient la clé ni un fragment.

### Interface
- Page Connecteurs : état sans clé, recherche, aperçu, application, lots,
  journal, erreurs de quota.
- Bandeau « aucune cote importée » visible.
- Responsive, navigation, absence d'erreur console.
- Aucune formulation certaine.

## Critères d'acceptation

1. La clé API est lue uniquement depuis l'environnement et n'apparaît ni en
   base, ni dans le frontend, ni dans les journaux, ni dans les réponses.
2. Une compétition peut être recherchée et associée à une compétition interne.
3. Le calendrier est prévisualisé avec ses compteurs et ses conflits avant
   toute écriture.
4. L'application d'un aperçu n'effectue aucune requête supplémentaire et ne
   crée aucun doublon en cas de réimport.
5. Les statistiques sont importées par lots dont le coût exact est affiché et
   le budget quotidien respecté.
6. Aucune cote, aucun marché et aucune sélection ne sont importés ou modifiés.
7. Une donnée manuelle n'est jamais écrasée ; les conflits sont listés.
8. Les identifiants externes, l'origine des données et le journal des
   synchronisations sont consultables.
9. Une base vide, une clé absente, un quota épuisé ou une saison non incluse
   produisent un message clair, jamais une erreur non maîtrisée.
10. Les combinaisons enregistrées restent lisibles et inchangées.
11. `ruff`, `mypy`, `pytest`, `eslint`, `tsc` et `next build` passent.
12. La documentation est à jour : `README.md`, `docs/exploitation/api.md`,
    `docs/exploitation/environnement.md` et `.env.example`.

## Livrables

- `apps/api/app/connectors/api_football/` : client, mapping, importateur,
  erreurs.
- `apps/api/app/services/connectors.py` : orchestration, aperçus, quotas,
  journal.
- `apps/api/app/schemas/connector.py` : schémas d'entrée et de sortie.
- `apps/api/app/api/v1/connectors.py` : routes et dépendances.
- `apps/api/app/models/connector.py` : `SyncRun`.
- Ajouts de colonnes sur les modèles existants et migration Alembic additive.
- `apps/api/app/core/config.py` : paramètres API-Football, clé facultative.
- `apps/web/src/app/(app)/connecteurs/page.tsx` : page complète.
- `apps/web/src/components/` : cartes d'état, aperçu, conflits, lots, journal.
- `apps/web/src/components/app-shell.tsx` : entrée « Connecteurs ».
- Tests moteur de mapping, client simulé, import SQLite, API et interface.
- Documentation d'exploitation et `.env.example`.

## Points soumis à validation

1. **Fournisseur** : API-Football, offre gratuite, 100 requêtes/jour.
2. **Budget** : 90 requêtes/jour maximum, lots de 10 statistiques.
3. **Priorité au manuel** : aucune donnée saisie n'est écrasée.
4. **Création des équipes** : proposée mais désactivable ; aucune fusion
   automatique en cas d'ambiguïté.
5. **Compétitions** : toujours associées ou créées sur choix explicite, jamais
   implicitement.
6. **Périmètre** : calendrier, résultats et statistiques uniquement ;
   **aucune cote**.

Après validation de ce plan, l'implémentation suivra l'ordre suivant :
migration et modèles, client et mapping testés hors réseau, importateur,
routes API, page Connecteurs, puis vérifications complètes et documentation.

## Annexe — étude d'une source de cotes 1xBet via RapidAPI

> **Décision en attente.** Cette annexe documente une demande d'extension du
> périmètre : importer aussi les cotes, et non plus seulement les rencontres et
> statistiques. Aucune implémentation ne sera lancée avant arbitrage explicite.

### Offres examinées

| Offre RapidAPI | Cotes 1xBet | Pré-match | Live | Résultats | Offre gratuite | Prix au-delà |
|---|---|---|---|---|---|---|
| **1xBet API** (Cosmx) | Oui | Oui (`line`) | Oui (`live`) | Oui | BASIC 0 $ (quota non publié) | PRO 15 $/mois, ULTRA 50 $/mois |
| **Sports Betting API** (bet365soft) | Oui, « powered by 1xBet » | Oui | Oui | Oui | BASIC 0 $ | non vérifié |
| **1XBet API Live odds** | Oui | Non | Oui uniquement | Non | BASIC 0 $ | PRO 5 $/mois |
| **Odds Feed** (tipsters) | Oui, parmi d'autres books | Oui | Oui | Oui | à confirmer | à confirmer |
| **OddsPapi** (via RapidAPI) | Oui | Oui | Oui | Non | 250 requêtes/mois | plans payants |

L'offre la plus complète est **1xBet API (Cosmx)** : sports, ligues,
rencontres, marchés (1X2, double chance, handicap, totaux, BTTS…), résultats
et événements live. Sa fiche indique explicitement :

> « This API is an unofficial service and is not affiliated with or endorsed
> by 1xBet. »

### Avantages

- Cotes **1xBet réelles**, ce qui correspond exactement au bookmaker utilisé.
- Pré-match et live, marchés nombreux, résultats et scores.
- Aucun identifiant ni compte 1xBet n'est nécessaire : seule une clé RapidAPI
  est utilisée.
- Offre gratuite pour tester ; PRO à 15 $/mois, moins cher qu'API-Football Pro.
- Intégration possible derrière la même abstraction de connecteur que les
  autres sources.

### Risques et limites

| Risque | Analyse |
|---|---|
| **Conformité** | Service non officiel, très probablement alimenté par scraping ou accès inverse aux flux 1xBet. Les conditions 1xBet interdisent l'usage d'outils automatisés pour interagir avec la plateforme. Le projet a une règle explicite : aucun scraping non autorisé de 1xBet. **Conflit direct.** |
| **Stabilité** | Une API non officielle peut être retirée, bloquée ou modifiée sans préavis. Le fournisseur peut disparaître de RapidAPI. |
| **Qualité des données** | Fraîcheur, exhaustivité et exactitude non garanties. Les identifiants de marchés et de sélections peuvent changer. |
| **Quota gratuit** | Le quota du plan BASIC n'est pas publié sur la fiche. Les plans gratuits RapidAPI de ce type sont souvent limités à 100–500 requêtes/mois, insuffisant pour un suivi quotidien de plusieurs compétitions. À confirmer avant tout engagement. |
| **Dépendance** | Si l'API disparaît, l'import des cotes cesse. Un mode manuel de secours reste indispensable. |
| **Sécurité** | La clé RapidAPI doit rester côté serveur, comme toute autre clé. Aucun mot de passe 1xBet n'est stocké. |
| **Maintenance** | Le mapping des marchés 1xBet vers le modèle interne (familles, lignes, sélections) est plus lourd qu'avec un fournisseur normalisé. Les tests devront figer des réponses réelles. |

### Verdict

Techniquement faisable et économiquement attractif, mais **non conforme à la
règle actuelle du projet** et **juridiquement/techniquement risqué**. Une API
non officielle de scraping ne peut pas être recommandée comme source
principale sans un arbitrage explicite de votre part.

### Alternatives conformes

1. **The Odds API** : agrégateur établi, 1xBet inclus (`onexbet`), 500 crédits
   gratuits par mois, conditions publiées. À combiner avec une source de
   calendrier/résultats (`football-data.org` gratuit ou API-Football payant).
2. **API-Football Pro** (~19 $/mois) : source unique, saison en cours, résultats,
   statistiques et cotes 1xBet (bookmaker n°11), 7 500 requêtes/jour.
3. **API-Football gratuit** : historique 2022-2024 uniquement, cotes
   inexploitables (pas de saison en cours, pas d'historique de cotes
   rétroactif), donc saisie manuelle conservée pour l'actualité.

### Décision requise

- **Option A** : renoncer à RapidAPI et retenir une alternative conforme.
- **Option B** : accepter explicitement le risque et utiliser RapidAPI comme
  source principale, avec avertissement dans l'interface, mode manuel de
  secours et possibilité de retirer le connecteur sans perte de données.
- **Option C** : utiliser RapidAPI uniquement en test, sans dépendance de
  production.

Tant que cette décision n'est pas prise, la Phase 7 reste au statut
« plan proposé » et aucune ligne de code n'est ajoutée.

# Phase 14A — Snapshots quotidiens BigBallsData

> **Statut : plan validé. 14A.1 et 14A.2 livrés le 14/11/2026 ; 14A.3 à 14A.6 à faire.**
>
> Objectif de la phase : **arrêter de dépendre de la mémoire du fournisseur** et
> constituer nous-mêmes l'historique dont le moteur a besoin pour être jugé.
> Cette phase ne modifie **ni le moteur, ni l'interface**. Elle collecte, stocke
> et journalise.

---

## 1. Pourquoi cette phase, et pourquoi maintenant

Les deux tests du 14/11/2026 ont donné le même verdict : **les signaux sont
réels, mais l'échantillon est trop petit pour trancher**.

| Test | Effet mesuré | Effet minimal détectable | Seuil du projet |
|---|---|---|---|
| Elo (1X2) | gain nul pour le moteur | 0,0062 | 0,003 |
| BTTS | +0,004 puis −0,003 | 0,0110 | 0,003 |
| Plus de 2,5 buts | +0,004 puis −0,003 | 0,0134 | 0,003 |

Deux constats en découlent :

1. **Rien ne pourra jamais être validé sans accumulation.** Chaque journée de
   championnat ajoute ~18 rencontres ; il en faut 650 évaluables pour le 1X2 et
   2 000 à 3 000 pour les marchés secondaires.
2. **Le fournisseur ne garde pas ce qu'on n'a pas demandé au bon moment.**
   `/v1/matches?season=2025` répond **403** sur le plan Free, et `/v1/games` ne
   donne les cotes **que des rencontres à venir**. Une journée non capturée est
   une journée perdue définitivement.

   Vérifié le 14/11/2026 sur l'API réelle : sans filtre, `/v1/matches?season=2026`
   ne renvoie **que les rencontres à venir** (216 en Ligue 1, toutes
   `scheduled`). En revanche `&status=finished` renvoie **toutes** les rencontres
   terminées de la saison : 90 en Ligue 1, 119 en Liga. La récupération des
   résultats est donc possible — à condition de demander explicitement ce filtre.

**Donc : collecter d'abord, conclure ensuite.** C'est l'inverse de ce qui a été
fait jusqu'ici, et c'est ce que la mesure impose.

### Ce que la phase 14A n'est pas

- Ce n'est **pas** une amélioration du moteur : `apps/api/engine/` ne bouge pas.
- Ce n'est **pas** une phase d'interface : aucune page, aucun composant.
- Ce n'est **pas** un passage à un plan payant.
- Ce n'est **pas** une collecte de cotes 1xBet : `/v1/games` reste l'étalon
  gratuit, étiqueté « marché agrégé, incomplet ».

---

## 2. Périmètre exact

| # | Livrable | Contenu | Effort |
|---|---|---|---|
| 14A.1 | Modèle + migration | 3 tables de snapshots, contraintes d'unicité, index | 0,5 j |
| 14A.2 | Collecteur de résultats | import des rencontres terminées de la saison, sans perte | 1 j |
| 14A.3 | Snapshots équipes et classements | Elo, stats, splits, classement du jour | 1 j |
| 14A.4 | Board marché, **deux relevés par jour** | cotes agrégées de `/v1/games`, 06 h 30 et 18 h 30 | 0,5 j |
| 14A.5 | Déclencheur quotidien | CLI réutilisable + planification Windows | 0,5 j |
| 14A.6 | Tests, journal, documentation | fixtures, idempotence, budget, doc d'exploitation | 1 j |
| | **Total** | | **4,5 j** |

Ordre imposé : 14A.1 → 14A.2 → 14A.3 → 14A.4 → 14A.5 → 14A.6. Chaque jalon est
livrable et testable seul.

---

## 3. Décisions techniques

| Décision | Choix | Justification |
|---|---|---|
| Où stocker | **PostgreSQL existant**, 3 tables dédiées | Pas de nouvelle base, pas de Docker, sauvegarde déjà en place |
| Nommage | anglais `snake_case` | Aligné sur `matches`, `team_match_stats`, `provider_usage` |
| Résultats | **réutiliser `matches`** | La table existe, l'importateur aussi : aucune duplication |
| Snapshots | **une ligne par entité et par jour** ; **deux créneaux** pour le board | Série temporelle simple, sans perte du second relevé de cotes |
| Idempotence | contrainte d'unicité + `ON CONFLICT DO NOTHING` | Un rejeu ne crée jamais de doublon |
| Déclencheur | **CLI Python + Planificateur de tâches Windows** | L'application web peut être fermée ; aucune dépendance nouvelle, pas de Docker |
| Journalisation | table `sync_runs` existante, opération `snapshots` | Déjà branchée sur les quotas et l'audit |
| Quota | budget par passe, arrêt propre si dépassé | Circuit breaker 4xx du fournisseur (500 erreurs/h) |
| Retry | 2 essais, backoff 5 s puis 30 s, jamais sur 4xx | Un 403/404 ne se répare pas en réessayant |
| Moteur | **aucune modification** | Règle du projet : un ajout n'entre qu'après validation statistique |

### Pourquoi deux relevés de cotes et pas un

Une cote relevée à 06 h 30 pour un match à 21 h **n'est pas une cote de
clôture**. Or c'est la clôture qui contient le plus d'information : c'est elle
que le backtest historique comparait aux colonnes `AvgC*` et `PSC*` des fichiers
publics. Avec un seul relevé le matin, l'étalon serait **systématiquement plus
faible** que celui du backtest, et l'écart au marché paraîtrait plus grand qu'il
ne l'est en réalité.

Deux relevés — 06 h 30 et 18 h 30 — permettent de retenir, pour chaque
rencontre, **le plus proche du coup d'envoi**. Coût : 4 requêtes de plus par
jour.

Les deux relevés sont **conservés séparément** : on ne remplace jamais le
premier par le second. Cela permet de mesurer plus tard l'effet du mouvement de
la cote entre le matin et le soir.

### Pourquoi pas un ordonnanceur dans l'API

Un `APScheduler` dans le processus FastAPI serait plus simple à écrire, mais il
ne tourne **que si l'application est ouverte**, et il meurt avec elle. Sur un
poste Windows personnel, la collecte quotidienne doit fonctionner sans que
l'utilisateur pense à lancer quoi que ce soit. Deux tâches planifiées — 06 h 30
et 18 h 30 — qui appellent un script, elles, fonctionnent même après un
redémarrage.

---

## 4. Modèle de données

### 4.1 `team_snapshots` — force et fréquences d'une équipe, par jour

| Colonne | Type | Nullable | Rôle |
|---|---|---|---|
| `id` | uuid | non | clé |
| `team_id` | uuid → `teams.id` | non | équipe interne |
| `captured_on` | date | non | **jour de capture** (Europe/Paris) |
| `captured_at` | timestamptz | non | horodatage exact |
| `source_as_of` | timestamptz | oui | `as_of` renvoyé par le fournisseur |
| `elo_rating` | numeric(7,2) | oui | force ajustée à l'adversaire |
| `elo_games_counted` | integer | oui | profondeur de la note |
| `elo_last_match_date` | date | oui | fraîcheur de la note |
| `matches_played` | integer | oui | taille de l'échantillon |
| `btts_rate` | numeric(5,4) | oui | fréquence BTTS |
| `over_2_5_rate` | numeric(5,4) | oui | fréquence plus de 2,5 |
| `goals_scored` | integer | oui | buts marqués |
| `goals_conceded` | integer | oui | buts encaissés |
| `clean_sheets` | integer | oui | cages inviolées |
| `form_string` | varchar(10) | oui | 5 derniers résultats |
| `home_wins`, `home_draws`, `home_losses` | integer | oui | splits domicile |
| `away_wins`, `away_draws`, `away_losses` | integer | oui | splits extérieur |

Contrainte : `UNIQUE (team_id, captured_on)`.

### 4.2 `standings_snapshots` — classement, par jour

| Colonne | Type | Nullable | Rôle |
|---|---|---|---|
| `id` | uuid | non | clé |
| `competition_id` | uuid → `competitions.id` | non | |
| `season_id` | uuid → `seasons.id` | non | |
| `team_id` | uuid → `teams.id` | non | |
| `captured_on` | date | non | |
| `rank` | integer | oui | position |
| `played`, `wins`, `draws`, `losses` | integer | oui | bilan |
| `points`, `goals_for`, `goals_against` | integer | oui | force de saison |
| `form_string` | varchar(10) | oui | |

Contrainte : `UNIQUE (team_id, season_id, captured_on)`.

**Intérêt** : le classement est le **seul historique profond accessible
gratuitement** (13 saisons, section 2.3 de l'étude). Stocké chaque jour, il
permet de reconstruire une force de début de saison et de mesurer l'enjeu.

### 4.3 `market_board_snapshots` — cotes agrégées, par rencontre et par jour

| Colonne | Type | Nullable | Rôle |
|---|---|---|---|
| `id` | uuid | non | clé |
| `match_id` | uuid → `matches.id` | non | rencontre interne |
| `external_match_id` | varchar(100) | non | identifiant fournisseur |
| `captured_on` | date | non | |
| `snapshot_slot` | varchar(10) | non | `morning` ou `evening` |
| `captured_at` | timestamptz | non | |
| `odds_updated_at` | timestamptz | oui | fraîcheur de la cote |
| `books_count` | integer | oui | nombre de books agrégés |
| `home_decimal` | numeric(7,3) | oui | cote domicile |
| `away_decimal` | numeric(7,3) | oui | cote extérieur |
| `total_line` | numeric(3,1) | oui | ligne de total |
| `over_decimal` | numeric(7,3) | oui | cote « plus » |
| `under_decimal` | numeric(7,3) | oui | cote « moins » |

Contrainte : `UNIQUE (match_id, captured_on, snapshot_slot)`. Les deux relevés
d'une même journée **coexistent** : le second n'écrase jamais le premier.

**Rappel** : pas de cote de nul, parfois une seule issue, parfois `odds: null`.
La colonne absente reste `NULL` — **jamais zéro**, jamais extrapolée.

### 4.4 Ce qui n'est pas créé

- **Pas** de table de résultats : `matches` la porte déjà.
- **Pas** de table de compositions ni de blessures : l'étude a montré qu'elles
  ne sont pas utilisables pour prédire (24 min avant le match, cache 6 jours).
- **Pas** de table de cotes 1xBet : hors périmètre depuis la décision du
  14/11/2026.

---

## 5. Collecte : quoi appeler, combien de fois

| Étape | Endpoint | Fréquence | Requêtes/passe |
|---|---|---|---|
| Résultats de la saison | `/v1/matches?sport=football&league=&season=2026&status=finished&limit=200&offset=` | 1×/jour | 2 (une page par ligue) |
| Snapshots équipes | `/v1/teams/{id}/elo`, `/stats`, `/season` | 1×/jour | 38 équipes × 3 = **114** |
| Classements | `/v1/standings?league=&season=2026` | 1×/jour | 2 |
| Board marché | `/v1/games?league=&date=` | **2×/jour**, J et J+1 | 8 |
| Vérification | `/v1/usage` | fin de passe | 1 |
| | | **Total** | **≈ 129 / jour** |

**Budget** : 129 sur 2 000, soit **6,5 %**. Marge suffisante pour les imports
manuels de l'application et pour une seconde passe de rattrapage. Une saison
complète dépassant 200 rencontres terminées, la pagination s'ajoute en fin de
saison : au pire 2 pages par ligue, soit 133 requêtes.

**Croissance des tables** : 38 équipes × 365 = ~13 900 lignes/an
(`team_snapshots`), ~27 800 (`standings_snapshots`, 2 compétitions), ~14 000
(`market_board_snapshots`, deux relevés par jour sur ~20 rencontres).
Négligeable pour PostgreSQL.

### 5.1 Le point critique : ne perdre aucun résultat

L'import actuel ne prend que les rencontres de la **fenêtre de 10 jours**
(`FIXTURE_WINDOW_DAYS`). Si le script ne tourne pas une semaine, des rencontres
terminées sortent de la fenêtre et sont **perdues** — le plan Free ne permet pas
de les redemander plus tard.

Parade : une passe **« résultats de la saison »** qui demande toute la saison en
cours **filtrée sur `status=finished`**, page par page, et insère uniquement les
rencontres terminées absentes. Elle coûte 2 requêtes (une par ligue) et rend le
dispositif **auto-réparant** après une coupure de quelques jours.

Le filtre est indispensable : sans lui, l'endpoint ne renvoie que les rencontres
à venir. C'est la vérification du 14/11/2026 qui l'a établi, et c'est elle qui
rend la promesse « aucun résultat perdu » tenable sur le plan gratuit.

---

## 6. Déroulé d'une journée

Deux passes, deux rôles. Le matin collecte tout ; le soir ne rafraîchit que les
cotes, pour se rapprocher de la clôture.

```
06:30  PASSE COMPLÈTE
       ├─ 1. résultats de la saison          (2-4 req)  → matches
       ├─ 2. snapshots des 38 équipes        (114 req)  → team_snapshots
       ├─ 3. classements des 2 ligues        (2 req)    → standings_snapshots
       ├─ 4. board marché J et J+1, matin    (4 req)    → market_board_snapshots (morning)
       └─ 5. quota + résumé dans sync_runs   (1 req)

18:30  PASSE BOARD SEULE
       ├─ 1. board marché J et J+1, soir     (4 req)    → market_board_snapshots (evening)
       └─ 2. quota + résumé dans sync_runs   (1 req)
```

Pourquoi cette asymétrie :

- une seule passe complète par jour suffit : Elo, stats et classements ne
  changent qu'après une rencontre, pas entre 06 h 30 et 18 h 30 ;
- la passe du soir ne coûte que **5 requêtes** et capture les cotes au moment où
  elles se rapprochent le plus du coup d'envoi ;
- si la passe du soir échoue, la journée reste exploitable avec le relevé du
  matin — il n'y a jamais de trou, seulement un relevé moins frais.

Règles communes :

- chaque étape est **indépendante** : l'échec de l'une n'arrête pas les autres ;
- une étape déjà faite pour **ce créneau** ne se refait pas (sauf `--force`) ;
  `--force` peut donc soit rejouer toute la passe, soit rejouer un seul créneau ;
- après 3 réponses 429 consécutives, la passe **s'arrête proprement** et écrit
  `status = "partial"` avec la raison ;
- un 403 ou un 404 **n'est jamais réessayé** : il est journalisé et l'entité est
  sautée ;
- le script **n'affiche jamais** la clé d'API, même en cas d'erreur HTTP.

---

## 7. Impact sur l'existant

| Élément | Impact |
|---|---|
| `apps/api/engine/` | **aucun** — le moteur reste pur et inchangé |
| `apps/web/` | **aucun** — aucune page, aucun composant |
| `matches`, `team_match_stats` | lectures et insertions via l'importateur existant |
| `sync_runs`, `provider_usage` | réutilisés, opération `snapshots` |
| Migrations | **une seule** révision additive, réversible |
| CI | tests sur fixtures, aucune clé réelle, aucun appel réseau |
| Version du projet | reste **1.1.0** (aucune version ni Release sans accord) |

---

## 8. Tests prévus

| Type | Ce qui est vérifié |
|---|---|
| Unitaire | transformation d'une réponse figée (`elo`, `stats`, `season`, `standings`, `games`) en lignes |
| Unitaire | `btts_rate` absent ou `null` → colonne `NULL`, jamais 0 |
| Unitaire | `odds: null` → aucune ligne de board, la rencontre n'est pas comptée comme cotée |
| Idempotence | deux passes **du même créneau** le même jour → **même nombre de lignes**, aucun doublon |
| Idempotence | passe du matin puis passe du soir → **une ligne de plus par rencontre cotée**, pas un remplacement |
| Idempotence | rejeu après suppression d'une ligne → la ligne est recréée |
| Quota | budget dépassé → arrêt propre, `status = "partial"`, aucune exception non gérée |
| Panne | 429 × 3 → arrêt ; 403 → entité sautée, passe poursuivie |
| Sécurité | aucun journal ne contient la clé d'API (test dédié) |
| Fenêtre | un résultat ancien (hors des 10 jours) est **quand même** récupéré |
| Filtre | une rencontre non terminée renvoyée par erreur est **écartée**, jamais écrite |
| Pagination | une saison de plus de 200 résultats est lue sur plusieurs pages, sans doublon |
| Migration | `upgrade` puis `downgrade` sur base de test, sans perte |

Vérification finale sur la base réelle : une passe complète doit produire
**38 lignes** dans `team_snapshots`, **38** dans `standings_snapshots`, et un
board non vide pour au moins une rencontre cotée. Après la passe du soir, cette
rencontre doit avoir **deux lignes** — `morning` et `evening`.

---

## 9. Critères d'acceptation

La phase 14A est considérée comme livrée si, et seulement si :

1. `pytest` et `ruff` verts, **aucun test ne touche le réseau** ;
2. `git diff apps/api/engine` est **vide** ;
3. une passe complète consomme **≤ 200 requêtes** et laisse un résumé lisible
   dans `sync_runs` ;
4. un rejeu immédiat ne crée **aucune ligne** supplémentaire ;
5. après 7 jours consécutifs, **≥ 95 %** des rencontres terminées de la saison
   sont en base ;
6. aucun identifiant de bookmaker, aucune clé d'API, aucun scrape non autorisé ;
7. la documentation d'exploitation explique comment **relancer une passe** et
   comment **vérifier qu'elle a tourné**.

---

## 10. Risques et parades

| Risque | Probabilité | Effet | Parade |
|---|---|---|---|
| Les deux relevés ne sont **pas** des clôtures strictes | certaine | étalon plus faible que celui du backtest | retenir le relevé le plus proche du coup d'envoi et **documenter l'écart** ; ne jamais présenter l'écart au marché comme identique à celui du backtest |
| Relevé du soir après le coup d'envoi (match à 19 h) | moyenne | cote en cours de rencontre | jeter tout relevé dont `captured_at` dépasse le coup d'envoi |
| Le poste est éteint à 06 h 30 | élevée | jour manqué | rattrapage automatique : la passe récupère les résultats de toute la saison |
| Quota épuisé par un import manuel | faible | passe partielle | budget lu avant la passe, arrêt propre, reprise le lendemain |
| Circuit breaker 4xx (500 erreurs/h) | faible | blocage 10 min | jamais de retry sur 4xx |
| `team_id` nul dans `/statistics` | observée | jointure cassée | non concerné ici : snapshots par identifiant d'équipe, pas par nom |
| Changement de saison (rollover août) | certaine, une fois par an | `season=2026` devient vide | détecter le passage via `/v1/standings` et basculer sur la nouvelle saison |
| Le fournisseur change un champ | moyenne | colonne vide | `NULL` autorisé partout, aucune exception levée sur un champ manquant |
| Les noms d'équipes diffèrent de ceux déjà en base | **élevée** | équipes dupliquées, rencontres en double | vérifié le 14/11/2026 : sur 18 clubs de Ligue 1, **5 ne s'apparient pas** en égalité stricte (`Brest`/`Stade Brestois 29`, `Lyon`/`Olympique Lyonnais`, `Marseille`/`Olympique de Marseille`, `Stade Rennais`/`Stade Rennais FC 1901`, `Strasbourg`/`RC Strasbourg Alsace`) ; **créer les liens BigBallsData après appariement manuel** de ces cinq équipes, jamais avant |
| Croissance des tables | faible | ralentissement | volume négligeable ; index sur `(captured_on)` et `(team_id, captured_on)` |
| Faux sentiment de progrès | **élevée** | on croit mesurer | aucun calcul de gain dans 14A : elle stocke, elle ne conclut pas |

---

## 11. Ce que 14A ne fait pas

- Aucune modification du moteur, des probabilités ou du générateur.
- Aucun nouvel écran, aucun graphique.
- Aucun backtest : la phase stocke, elle ne mesure rien.
- Aucune introduction d'Elo, de fréquences d'équipe ou de classement dans le
  moteur — ces signaux restent hors du moteur jusqu'à validation.
- Aucun passage à un plan payant.

---

## 12. Ce que 14A rend possible

| Après | Échéance réaliste | Ce qu'on pourra dire |
|---|---|---|
| ~650 rencontres évaluables | **mai 2027** (fin de saison, 2 ligues) | l'Elo et le mélange sont-ils mesurables sur le 1X2 ? |
| ~1 300 rencontres | fin 2027 | les forces de début de saison réduisent-elles le biais favori–outsider ? |
| 2 000 à 3 000 rencontres | **hors d'atteinte en gratuit** | les fréquences d'équipe valent-elles mieux que le moteur sur BTTS et totaux ? |

Conséquence à assumer clairement : **le gratuit suffit pour le 1X2, pas pour les
marchés secondaires.** Si BTTS et totaux doivent être tranchés, ce sera contre
un mois de plan Solo (19 $) ou pas du tout — et ce choix se posera en
**mai 2027**, pas maintenant.

---

## 13. Validation demandée

Avant d'écrire la moindre ligne de code, trois points doivent être validés :

1. **Le périmètre** — 3 tables, 1 CLI, 0 interface, 0 moteur.
2. **Le déclencheur** — Planificateur de tâches Windows : une passe complète à
   06 h 30, une passe board seule à 18 h 30, plutôt qu'un ordonnanceur dans
   l'API.
3. **L'arrêt** — la phase se termine sans aucune conclusion statistique. Elle ne
   sert qu'à rendre les tests de 2027 possibles.

Si ces trois points sont acceptés, l'implémentation commence par 14A.1
(modèle + migration), qui est réversible et ne touche à rien d'existant.

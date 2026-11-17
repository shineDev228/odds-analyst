# Phase 15 — Reconstruction sur BigBallsData

> **Statut : étapes 1 à 3 livrées. Étapes 4 à 7 à faire (16/11/2026).**
>
> Objectif : **repartir d'une base propre, construite autour d'une source
> unique de faits** (BigBallsData), en supprimant l'appariement d'équipes qui a
> bloqué toutes les tentatives précédentes.
>
> Cette phase **ne modifie ni le moteur statistique, ni l'interface**, à
> l'exception de la page Connecteurs, remplacée par une page Synchronisation.

---

## 1. Pourquoi repartir de zéro

La base actuelle est un assemblage de trois fournisseurs : 119 rencontres issues
de football-data.org, 90 rencontres et leurs statistiques issues d'un CSV, 30
cotes issues de The Odds API. Cet assemblage impose de faire converger des noms
d'équipes écrits différemment — et c'est là que tout se bloque.

Mesures du 14 et 15/11/2026 :

| Constat | Valeur |
|---|---|
| Rencontres en base | 221 (209 terminées) |
| Statistiques en base | 180 lignes, **une seule ligue** |
| Équipes à réconcilier | 38, dont **5 en conflit de nom** |
| Résultats disponibles chez BigBallsData | **972** |
| Effet minimal détectable (1X2) | 0,006 pour 152 rencontres évaluables |
| Seuil du projet | 0,003 |

Repartir de zéro ne fait pas seulement « nettoyer » : avec 972 résultats,
environ 730 seront évaluables, ce qui ramène l'effet minimal détectable à
**≈ 0,0027**, sous le seuil du projet. **C'est la première fois que le moteur
devient jugeable.** C'est l'argument décisif de la phase.

---

## 2. Les trois sources, et leur rôle exact

Une seule source de **faits**, deux usages périphériques strictement bornés.

| Source | Rôle | Plan | Ce qu'elle ne fait jamais |
|---|---|---|---|
| **BigBallsData** | Résultats, statistiques, classements, équipes, logos, journées | Free | Fournir xG ou cotes |
| **CSV football-data.co.uk** | xG et cotes de clôture, en enrichissement | Gratuit, fichier public | Créer une équipe ou une rencontre |
| **The Odds API** | Marché des rencontres **à venir** | Free, 400 crédits/mois | Alimenter les notes des équipes |

### 2.1 Ce que BigBallsData fournit réellement (vérifié)

| Élément | Endpoint | Plan |
|---|---|---|
| Rencontres (à venir et terminées) | `/v1/matches` | Free |
| Statistiques par équipe, 18 champs | `/v1/matches/{id}/statistics` | Free |
| Classements | `/v1/standings` | Free |
| Équipes et logos | `/v1/teams` | Free |
| Buteurs | `/v1/leagues/{id}/top-scorers` | Free |
| **xG** | `/statistics` | **Solo+ (omis, jamais nul)** |
| **Cotes exploitables** | `/v1/matches/{id}/odds` | **Edge+ (403 en dessous)** |
| Bandeau de cotes agrégées | `/v1/games` | Free, plafonné à ~15-20 matchs/sport/jour |

Conséquences actées :

- le **xG ne vient pas** de BigBallsData : il vient du CSV, sur la même ligne
  que le score ;
- les **cotes ne viennent pas** de BigBallsData : `/v1/games` est un bandeau
  d'interface, pas un flux de marché ;
- le chemin `/stats` utilisé par le code actuel **n'existe pas** (404) : les
  statistiques BigBallsData n'ont jamais été importées. Le bon chemin est
  `/statistics`.

### 2.2 Le CSV porte plus que le xG

Une ligne du fichier 2026-27 contient `HxG`, `AxG`, les tirs, les corners, les
cartons **et les cotes** : Bet365, moyennes, maxima, et surtout les cotes de
**clôture** (`B365CH/CD/CA`, `AvgCH/CD/CA`).

La clôture est le meilleur étalon qui existe. Pour juger le moteur sur
l'historique, le CSV suffit donc à lui seul : **xG et marché, sur la même
ligne, sans appariement supplémentaire**.

The Odds API ne sert plus que pour les rencontres **à venir**.

---

## 3. Pourquoi l'appariement cesse d'être un problème

Trois appariements subsistent, de trois natures différentes. Aucun ne peut
créer d'entité.

### 3.1 BigBallsData → base : **aucun appariement**

L'UUID du fournisseur est stocké dans `teams.external_id` et
`matches.external_id`, en colonne unique. L'équipe de la base **est** l'équipe
du fournisseur : même identifiant, même nom, même logo.

Il n'y a plus deux populations à réconcilier, donc plus de conflit
`Brest` / `Stade Brestois 29`. Le problème n'est pas résolu : **il n'existe
plus.**

### 3.2 CSV → rencontre : appariement par le score

La rencontre est identifiée par **(ligue, date exacte, score final, score à la
mi-temps)**. Le nom ne sert qu'à confirmer le sens domicile/extérieur.

Mesuré sur les fichiers 2026-27 :

| | Ligue 1 | La Liga | Total |
|---|---|---|---|
| Lignes CSV | 90 | 119 | 209 |
| Rattachées automatiquement | 90 | 118 | **208 (99,5 %)** |
| À confirmer une fois | 0 | 1 | 1 |
| Échecs | 0 | 0 | 0 |

Le seul doute (`Rennes - Lille`, 08/11) vient de deux matchs terminés 1-2 le
même jour, avec `Rennes` côté CSV et `Stade Rennais` côté BigBallsData. Le
système choisit le bon mais sa marge est de 0,18 : il demande au lieu de
deviner. La décision est enregistrée et n'est plus jamais reposée.

Une rencontre BigBallsData n'a pas de ligne CSV (match de coupe dans le flux
`laliga`) : elle n'aura simplement pas de xG.

**Règle dure** : en cas de doute — deux candidats à moins de 0,25 d'écart — on
n'écrit **rien**. Un xG manquant ne coûte rien ; un xG faux coûterait la
crédibilité du moteur.

### 3.3 The Odds API → rencontre : appariement par le coup d'envoi

Clé composite : **(compétition, coup d'envoi ± 15 min)**, puis score de nom
pour départager les matchs simultanés, puis marge minimale de 0,10. Un écart de
nom trop fort, ou deux candidats à moins de 0,10 l'un de l'autre, ne produit
**aucune** décision : l'événement est listé comme ambigu et rien n'est écrit.

Mesuré le 15/11/2026 sur 38 événements réels (Ligue 1 + Liga), puis vérifié le
17/11/2026 sur les **122 événements des sept compétitions** :

| Résultat | 15/11 (38) | 17/11 (122) |
|---|---|---|
| Rattachés automatiquement | **38 / 38** | **118 / 122** |
| Marge minimale observée | 0,60 | 0,60 |
| Marge médiane | 1,00 | 1,00 |
| Orientation domicile/extérieur correcte | 38 / 38 | 118 / 118 |
| Ambigus | 0 | 0 |

Cas les plus difficiles, tous résolus : `Rennes` → `Stade Rennais` (0,90),
`Athletic Bilbao` → `Athletic Club` (0,71), `CA Osasuna` → `Osasuna` (0,90),
`Brighton & Hove Albion` → `Brighton and Hove Albion` (1,00, après la
normalisation `&`/`and`).

Les **quatre** événements non rattachés du 17/11 ne sont pas des erreurs
d'appariement : trois reposent sur un exonyme que la base n'emploie pas
(`1. FC Köln` = `FC Cologne`, `Sporting Lisbon` = `Sporting Clube de Portugal`,
`AEK Athens` non présent sous ce libellé), et un n'a **aucun** candidat dans la
compétition (Como – AEK, alors que Como est en Serie A dans la base). Aucun
alias n'est codé en dur : ils restent visibles dans l'interface, sans cote.

Une décision enregistrée dans `odds_event_links` n'est **jamais** reposée.

### 3.4 Pourquoi une erreur de cote est bénigne

Les cotes ne nourrissent jamais les notes des équipes. Elles servent à
l'affichage et à la comparaison au marché. Une erreur de cote est visible,
isolée et réversible ; une erreur de résultat ne l'est pas. C'est ce qui permet
d'être tolérant sur les cotes et strict sur les faits.

---

## 4. Architecture cible

Le schéma actuel est sain : il est encombré par le multi-fournisseur. On
l'allège au lieu de le jeter.

```
sports          code · name
competitions    id · code BBD ('ligue1') · name · country · tier · is_active
seasons         id · competition_id · label ('2026-2027') · external_label ('2026')
teams           id · external_id BBD (unique) · name · short_name · logo_url
matches         id · external_id BBD (unique) · season_id · journee · kickoff_at
                status · score · mi-temps · affluence · diffusion · has_odds
team_match_stats  match_id · team_id · is_home · 18 colonnes · extra JSON
csv_links       ligne CSV → rencontre (méthode, confiance, décidé le)
odds_event_links événement de cotes → rencontre (méthode, confiance)
snapshots       team_snapshots · standings_snapshots   (livrés en 14A.1)
sync_runs       journal des passes · provider_usage     (conservés)
```

### 4.1 Colonnes ajoutées à l'existant

| Table | Colonnes |
|---|---|
| `competitions` | `code` (unique, ex. `ligue1`) |
| `seasons` | `external_label` (ex. `2026`) |
| `teams` | `external_id` (unique), `logo_url` |
| `matches` | `external_id` (unique), `round_name`, `broadcast`, `attendance`, `has_odds` |
| `team_match_stats` | `shots_off_target`, `blocked_shots`, `shots_inside_box`, `shots_outside_box`, `fouls`, `offsides`, `passes`, `accurate_passes`, `pass_percentage`, `goalkeeper_saves` |

`shots` reste le total de tirs (nom historique conservé), `possession` reste
`ball_possession` du fournisseur.

Les colonnes `external_id` sont **nullables mais uniques**. C'est volontaire :
la saisie manuelle et les rencontres importées avant la reconstruction n'ont
pas d'identifiant BigBallsData, et doivent continuer de fonctionner. Sur
PostgreSQL comme sur SQLite, une contrainte d'unicité laisse passer plusieurs
valeurs nulles. L'obligation « toute rencontre importée porte un `external_id` »
est donc portée par l'importeur et par ses tests, pas par le schéma — un schéma
ne peut pas distinguer une ligne manuelle d'une ligne importée.

### 4.2 Colonnes qui resteront vides, et pourquoi

| Colonne | Raison |
|---|---|
| `matches.venue`, `matches.referee` | absents du flux BigBallsData |
| `team_match_stats.expected_goals` | absent de BigBallsData, rempli par le CSV |
| `team_match_stats.possession` | fourni à partir de maintenant, vide pour l'historique importé d'ailleurs |

Aucune colonne n'est inventée : une valeur absente reste `NULL`.

### 4.3 Tables supprimées en fin de phase

| Table | Raison |
|---|---|
| `provider_refs` | remplacée par `external_id` et les deux tables de liens |
| `connector_links` | plus aucun fournisseur à configurer : BigBallsData est unique |

`sync_runs` et `provider_usage` restent : ce sont le journal et le quota, pas
un annuaire de fournisseurs.

La suppression effective a lieu à l'étape 2, quand plus aucun code ne les lit.
Elle n'a lieu qu'après la reconstruction des données, jamais avant.

---

## 5. Déroulé de la phase

| Étape | Contenu | Critère de sortie |
|---|---|---|
| **1** | Schéma v2 : colonnes ajoutées, `csv_links`, `odds_event_links`, migration réversible, modèles, tests de schéma | **livrée** — migration validée en upgrade/downgrade sur base temporaire |
| **2** | Importeur BigBallsData unique (`/matches`, `/statistics`, `/standings`, `/teams`), suppression de `provider_refs` et `connector_links` | tests sur charges réelles enregistrées |
| **3** | Reconstruction réelle : 7 compétitions, ≈ 1 000 requêtes | **réalisée le 16/11** — 971 résultats, 0 doublon, 0 équipe hors BigBallsData ; **113 statistiques relancées le 17/11 : le fournisseur n'en a aucune**, dossier clos |
| **4** | Appariement des cotes par clé composite, import 1xBet borné, panneau de synchronisation | **réalisée le 17/11** — 118/122 événements rattachés, 26 liens, 56 marchés, 230 relevés, 10 crédits consommés |
| **5** | Enrichissement CSV : xG et cotes de clôture | 209 lignes traitées, 208 automatiques, 1 décision |
| **6** | Page Synchronisation (remplace Connecteurs) + CLI | **page livrée avec l'étape 2** ; CLI à faire |
| **7** | Vérification et documentation d'exploitation | comptages, intégrité, moteur et interface inchangés |

### 5.1 Budget de requêtes

| Passe | Requêtes |
|---|---|
| Reconstruction initiale (7 compétitions) | ≈ 1 000 |
| Statistiques des rencontres terminées | ≈ 970 |
| Passe quotidienne (résultats + nouveaux matchs) | ≈ 45 |

Quota : 2 000 par jour chez le fournisseur, plafond local **1 800** (10 % de
marge) et 100 requêtes par minute, ramenées à 75 par l'attente de 0,8 seconde.
La reconstruction tient en deux séances d'une dizaine de minutes.

The Odds API se compte en **crédits**, pas en requêtes : un appel compétition
(1X2 + totaux) coûte **2 crédits**, un appel événement (double chance + BTTS)
coûte **2 crédits**, et la liste des événements est **gratuite**. Un plafond
local de **400 crédits par mois** protège le compte ; l'aperçu ne consomme rien.

---

## 6. Risques et parades

| Risque | Probabilité | Effet | Parade |
|---|---|---|---|
| Perte des xG pour les ligues sans CSV | moyenne | moteur au niveau « tirs cadrés » | assumé et affiché ; le moteur bascule automatiquement |
| Deux matchs même jour, même score | moyenne | xG sur le mauvais match | marge de 0,25, sinon aucune écriture |
| Match de coupe dans un flux de championnat | certaine | une rencontre sans xG | toléré, compté dans le rapport de passe |
| Relevé The Odds API indisponible | moyenne | combinaisons sans cote | passe marquée `partial`, jamais de cote inventée |
| Exonyme non reconnu (`FC Cologne`, `Sporting Lisbon`) | certaine | événement sans cote | aucune devinette : l'événement reste listé « sans rencontre », rattachable à la main |
| Crédits The Odds API épuisés | faible | import partiel | plafond local 400, aperçu gratuit obligatoire avant la passe, arrêt propre |
| Cote réactualisée entre deux passes | certaine | un relevé de plus | historique append-only : aucune cote passée n'est écrasée |
| Quota épuisé pendant la reconstruction | faible | import partiel | reprise automatique : la passe ne réécrit que ce qui manque |
| Report d'un match : l'événement de cotes garde l'ancienne heure | faible | cote non rattachée | repli sur le nom seul dans la compétition, marqué `name_fallback` |
| Suppression prématurée de `provider_refs` | faible | application cassée | suppression à l'étape 2 seulement, après la reconstruction |
| Confusion xG fournisseur / xG CSV dans l'interface | moyenne | lecture erronée | la source du xG est affichée sur la fiche de rencontre |

---

## 7. Tests

| Type | Ce qui est vérifié |
|---|---|
| Schéma | `external_id` unique sur équipes et rencontres ; un doublon est refusé |
| Schéma | un événement de cotes ne peut être lié qu'à une rencontre |
| Schéma | une ligne CSV ne peut être appliquée qu'une fois (`source` + `row_key`) |
| Schéma | une rencontre ne reçoit qu'un seul xG ; la seconde écriture est refusée |
| Appariement | les 38 cas The Odds API mesurés sont rejoués, 38/38 |
| Appariement | les 16 décisions réelles du 17/11 sont figées en fixture et rejouées à l'identique (12 rattachements, 4 refus) |
| Appariement | `Brighton & Hove Albion` et `Brighton and Hove Albion` donnent le même nom normalisé |
| Appariement | `Manchester City` / `Manchester United` restent sous le seuil (0,55) |
| Appariement | les 209 lignes CSV mesurées : 208 automatiques, 1 en attente |
| Appariement | deux candidats à moins de 0,25 d'écart → aucune écriture, ligne journalisée |
| Import | rejeu immédiat d'une passe → aucune ligne créée, aucun doublon |
| Import | une cote réactualisée crée un relevé de plus, jamais un second marché |
| Import | une saisie manuelle n'est jamais écrasée par l'import |
| Import | une rencontre créée porte obligatoirement un `external_id` |
| Import | quota épuisé → arrêt propre, `status = "partial"` |
| Sécurité | aucun journal ne contient la clé d'API |
| Migration | `upgrade` puis `downgrade` sur base temporaire, sans perte |

---

## 8. Invariants

1. Aucune équipe ni rencontre ne peut être créée par un CSV ou par The Odds API.
2. Toute rencontre BigBallsData porte un `external_id` unique et non nul.
3. Une rencontre a au plus un lien de cotes actif.
4. En cas de doute d'appariement, aucune écriture : la ligne est journalisée.
5. Une valeur absente reste `NULL` ; rien n'est interpolé, rien n'est déduit.
6. Le moteur ne lit jamais les cotes.

---

## 9. Ce que la phase ne fait pas

- elle ne modifie pas le moteur statistique ;
- elle ne modifie pas les pages de l'interface, hors Connecteurs → Synchronisation ;
- elle ne change pas la version du projet (reste **1.1.0**) ;
- elle ne conclut rien statistiquement : elle prépare l'échantillon ;
- elle ne crée ni Release ni publication sans accord explicite.

---

## 10. Journal de la phase

### Étape 1 — schéma v2 (15/11/2026)

| Élément | État |
|---|---|
| Migration `c3f6a9b2e5d8` (après `a4f1c8d2e965`) | écrite, réversible |
| Modèles : `reference.py`, `match.py`, `link.py` | à jour |
| Tests de schéma (20) | verts |
| `ruff` sur `app` et `tests` | vert |
| `mypy app` | vert, 88 fichiers |
| Suite complète | verte |
| `alembic check` sur base temporaire | « No new upgrade operations detected » |
| Upgrade → downgrade → upgrade PostgreSQL | validé, index partiels présents, retour arrière complet |

Deux ajustements faits pendant l'étape :

1. **`external_id` nullable mais unique** : la saisie manuelle et les données
   antérieures n'ont pas d'identifiant fournisseur. L'unicité est garantie dès
   qu'une valeur existe ; l'obligation d'en avoir une est portée par l'importeur.
2. **Correction d'un test instable préexistant** : `test_save_rejects_started_match`
   utilisait `12:00 UTC - 1 h` comme coup d'envoi « passé ». Entre 00:00 et
   11:00 UTC, ce coup d'envoi est en réalité futur, et le test échouait. Il
   utilise désormais l'heure réelle moins une heure. Aucun code applicatif
   n'est concerné.

Aucune donnée de la base réelle n'a été modifiée : la migration n'a été jouée
que sur une base temporaire, créée puis supprimée.

### Étape 2 — importeur unique et suppression des correspondances (16/11/2026)

| Élément | État |
|---|---|
| `services/synchronization.py` | une passe par compétition, pages de 200, réessai sur 429, journal `sync_runs` par compétition |
| Client BigBallsData | `list_leagues`, `list_matches`, `get_statistics`, `list_teams`, `get_standings` |
| Mapping | mi-temps lue dans `linescore[0]`, `round`, `broadcast`, `attendance`, `has_odds` ; **xG volontairement ignoré** |
| Importateur | upserts idempotents ; adoption d'une équipe manuelle sans identifiant ; rencontre manuelle jamais modifiée |
| Routes | `GET /v1/sync/overview`, `GET /v1/sync/runs`, `POST /v1/sync/run` |
| Migration `e7b2d4c81f60` | suppression de `provider_refs`, `connector_links` et `sync_runs.link_id` |
| Ancien matériel | `services/connectors.py`, `services/collection.py`, `api/v1/connectors.py`, `schemas/connector.py`, `import_common.py`, `football_data/` et les importateurs CSV/cotes supprimés |
| Interface | page `synchronisation` (remplace `connecteurs`), types et navigation à jour |
| Tests | 14 tests sur charges réelles enregistrées dans `tests/fixtures/bbd/` |
| `ruff` et `mypy` | verts (79 fichiers) |
| Suite complète | verte — 269 tests |
| `npm run build` | réussi ; la page `synchronisation` est compilée |
| `alembic check` sur base temporaire | « No new upgrade operations detected » |
| Upgrade → downgrade → upgrade PostgreSQL | validé, retour arrière complet |

Décisions prises pendant l'étape :

1. **Le xG n'est jamais écrit par BigBallsData.** Le mapping l'ignore, et une
   passe de statistiques ne remplace pas un `expected_goals` déjà présent : il
   appartient au CSV.
2. **Les statistiques ne sont demandées que si elles manquent côté
   BigBallsData.** Le contrôle porte sur `team_match_stats.data_source` : une
   ligne écrite par le CSV n'empêche pas la mise à jour des autres champs.
3. **Les dates sont comparées en UTC.** SQLite rend les dates sans fuseau ; sans
   cette normalisation, chaque passe réécrivait les rencontres et le journal
   annonçait des mises à jour qui n'en étaient pas.
4. **Le budget local BigBallsData passe de 200 à 1 800 requêtes par jour.**
   Le fournisseur autorise 2 000 ; l'ancien plafond de 200 aurait bloqué la
   reconstruction de 972 rencontres. La marge de 10 % couvre les reprises.
5. **Une équipe manuelle sans identifiant est reprise, jamais dupliquée.** Si
   deux identifiants fournisseur différents portent le même nom, la
   compétition est marquée `failed` : aucune fusion devinée.
6. **Le délai d'un appel de synchronisation dans l'interface est porté à
   15 minutes.** Une passe complète avec statistiques dure plusieurs minutes à
   raison d'environ une requête par seconde ; le délai général reste de 60 s.

La base réelle reste à la révision `a4f1c8d2e965`. Les deux migrations seront
appliquées au début de l'étape 3, juste avant la reconstruction : la sauvegarde
`odds_analyst-20261114-232149.dump` couvre ce point de retour.

Étape 2 commitée sous `27ba363`.

### Étape 3 — reconstruction réelle (16/11/2026)

Les deux migrations `c3f6a9b2e5d8` puis `e7b2d4c81f60` ont été appliquées à la
base réelle : tête Alembic `e7b2d4c81f60`, `alembic check` sans opération
manquante, comptes inchangés avant purge (221 rencontres, 180 statistiques,
38 équipes). Une sauvegarde fraîche de cet état a été prise :
`infra/backups/odds_analyst-20261116-221021-avant-reconstruction.dump`.

#### La décision qui manquait au plan

La base contenait **221 rencontres de la saison 2026-2027**, la même que celle
fournie par BigBallsData : 131 importées de football-data.org et 90 issues du
CSV de Ligue 1. Ces lignes n'ont pas d'identifiant fournisseur, et la phase
supprime justement l'appariement par les noms. Les garder aurait produit deux
fois les mêmes rencontres, donc un moteur qui compte double.

Décision retenue, après validation : **repartir proprement**. Suppression des
221 rencontres, de leurs 180 lignes de statistiques, des 12 marchés, 30
sélections et 30 cotes qui en dépendaient, ainsi que des 38 équipes et du
référentiel de compétitions et de saisons. Ce qui disparaît réellement :

- les 30 cotes anciennes, qui seront reprises à l'étape 4 pour les rencontres
  à venir ;
- les 180 lignes de statistiques, dont le xG, rapporté par le CSV à l'étape 5.

Rien d'irremplaçable n'est perdu, et la sauvegarde permet un retour complet.
Les rencontres vraiment saisies à la main restent possibles : la règle
« une rencontre sans identifiant n'est jamais touchée par un import » est
conservée dans l'importeur et ses tests.

#### Passe calendrier et classements

Une passe unique sur les sept compétitions, sans statistiques, avec
classements : **28 requêtes** pour un quota restant de 1 772.

| Compétition | Rencontres | Terminées | Équipes | Classement |
|---|---|---|---|---|
| Ligue 1 | 306 | 90 | 18 | 18 |
| La Liga | 380 | 120 | 21 | 20 |
| Premier League | 380 | 100 | 20 | 20 |
| Serie A | 380 | 110 | 20 | 20 |
| Bundesliga | 306 | 81 | 18 | 18 |
| Ligue des champions | 148 | 76 | 16 | 32 |
| MLS | 414 | 394 | 32 | 30 |
| **Total** | **2 314** | **971** | **145** | **158** |

Les 971 résultats distincts sont conformes aux 972 mesurés le 15/11 : deux
rencontres de Ligue des champions se sont jouées entre-temps, et trois des
fiches importées étaient des copies dégradées de rencontres déjà présentes.
Contrôles : **0 identifiant de rencontre en doublon**, **0 équipe sans
identifiant BigBallsData**, 7 compétitions, 7 saisons.

#### Fiches en double chez le fournisseur

Le flux renvoie parfois **deux fiches pour une même affiche** : même saison,
mêmes équipes, même coup d'envoi, mais deux identifiants. Le contrôle a montré
que la règle est nette sur les 14 paires observées : **une seule fiche porte la
journée** (14/14), jamais les deux, jamais aucune. C'est aussi celle qui porte
le bon score et les statistiques ; la fiche dégradée affiche parfois un score
faux (`0:0` au lieu de `1:1` pour New York City – Los Angeles FC).

Traitement retenu :

- **à l'import**, si l'affiche existe déjà sous un autre identifiant, la fiche
  sans journée est ignorée et comptée (`duplicates`), avec un avertissement
  dans le journal ; si c'est la fiche complète qui arrive en second, elle prend
  l'identité de la fiche dégradée **sans changer la ligne**, donc sans perdre
  ses statistiques ;
- **en base**, les 14 fiches dégradées déjà importées ont été supprimées après
  vérification qu'elles ne portaient aucune statistique ni aucun lien.

Après nettoyage : **2 314 rencontres, 0 doublon**, dont 1 343 à venir.

#### Rencontres terminées sans score

Quatre rencontres de Ligue des champions (barrages et troisième tour
préliminaire, août 2026) sont marquées `termine` par le fournisseur **sans
aucun score** : Union Saint-Gilloise – Bodø/Glimt (aller et retour) et
Fenerbahçe – Lyon (aller et retour). Aucune autre fiche n'existe pour ces
affiches. Rien n'est inventé : elles restent sans score et le moteur les écarte,
puisqu'il ne travaille que sur des résultats connus. Elles sont aussi sans
statistiques.

#### Statistiques

Collecte ligue par ligue, 200 rencontres au plus par passe, soit **1 008
requêtes** pour les statistiques (94 + 124 + 104 + 114 + 85 + 79 + 204 + 204).
Avec les 28 de la passe calendrier, la journée consomme **1 036 requêtes** :
quota restant 764 sur 1 800.

| Compétition | Terminées | Avec statistiques | Sans statistiques |
|---|---|---|---|
| Ligue 1 | 90 | 90 | 0 |
| La Liga | 120 | 119 | 1 |
| Premier League | 100 | 100 | 0 |
| Serie A | 110 | 110 | 0 |
| Bundesliga | 81 | 81 | 0 |
| Ligue des champions | 76 | 57 | 19 |
| MLS | 394 | 301 | 93 |
| **Total** | **971** | **858** | **113** |

**1 716 lignes de statistiques** écrites : chaque rencontre couverte a ses deux
lignes, jamais une seule. Aucune valeur n'est inventée ; le xG reste vide
(0 ligne), il viendra du CSV.

Les 113 rencontres sans statistiques ne viennent pas d'une coupure de quota :
le compteur local indiquait encore 764 requêtes, et trois échantillons vérifiés
(une par ligue concernée) renvoient `{"home": null, "away": null}`. Le
fournisseur n'a donc pas de statistiques pour ces rencontres. La liste précise
est conservée dans `docs/etudes/phase15-stats-manquantes.json` (hors dépôt).

Le journal d'une passe signale désormais explicitement
« N rencontre(s) sans statistiques chez le fournisseur : aucune valeur n'est
inventée », et les compteurs `stats_missing` et `duplicates` sont exposés dans
le résumé.

Contrôles de sortie : `ruff` et `mypy` verts, **272 tests verts**,
`npm run build` réussi. Étape commitée sous `7b50599`.

#### Deuxième essai des 113 rencontres (17/11/2026)

Le quota étant réinitialisé (1 800 requêtes disponibles), les trois
compétitions concernées ont été relancées avec `stats_limit = 200` :

| Compétition | Rencontres demandées | Statistiques écrites | Requêtes | Quota restant |
|---|---|---|---|---|
| La Liga | 1 | 0 | 5 | 1 795 |
| MLS | 93 | 0 | 97 | 1 698 |
| Ligue des champions | 19 | 0 | 22 | 1 676 |
| **Total** | **113** | **0** | **124** | **1 676** |

**Le verdict est définitif : le fournisseur ne renvoie aucune statistique pour
ces 113 rencontres**, même quota neuf et une par une. La base est inchangée
(2 314 rencontres, 1 716 lignes de statistiques, 0 doublon, 0 xG). Les 113
restent donc vides et le resteront : rien n'est inventé.

La passe MLS a également signalé **14 fiches en double** : le fournisseur
renvoie toujours plusieurs fiches pour une même affiche, et la garde anti-doublon
les écarte comme prévu.

Conséquence pour le moteur : ces rencontres sont écartées du calcul (aucune
statistique à lire) et ne pénalisent pas les autres. Le moteur retombe sur le
proxy « tirs cadrés » puis sur les buts réels pour les rencontres couvertes.

#### Reste à faire sur l'étape 3

- **Rien de bloquant.** La relance des 113 rencontres est faite et close : le
  fournisseur ne les complétera pas. Aucune nouvelle tentative n'est utile.
- Les quatre rencontres de Ligue des champions terminées sans score (barrages
  d'août, Union SG – Bodø/Glimt et Fenerbahçe – Lyon, aller et retour) sont
  écartées par le moteur via `home_score IS NOT NULL`.
- Le xG reste à zéro ligne : il arrivera avec l'étape 5 (fichier CSV public).

#### Contrôle de lecture après reconstruction

Une prédiction réelle a été calculée sur **Troyes – Le Havre AC** (20/11/2026) :
buts attendus 1,41 + 1,14, domicile 43,0 % [20,0 ; 70,5], nul 26,7 %
[15,7 ; 32,1], extérieur 30,3 % [11,6 ; 54,7], BTTS oui 51,4 %
[32,2 ; 70,9]. Qualité « faible », cohérente avec 10 rencontres par équipe :
la saison vient de commencer et le moteur utilise le proxy « tirs cadrés » tant
que le xG n'est pas fourni par le CSV. Les fourchettes larges sont donc
attendues à ce stade.

### Étape 4 - cotes 1xBet des rencontres à venir (17/11/2026)

#### Ce que fait la passe

1. **Aperçu gratuit** : la liste des événements de chaque compétition est
   gratuite. L'appariement est calculé à blanc, sans écrire et sans payer.
2. **Passe payante** : pour chaque compétition retenue, un appel
   « compétition » (2 crédits) ramène le 1X2 et les totaux de tous ses
   événements. Les marchés étendus (double chance, « les deux équipes
   marquent ») coûtent 2 crédits **par événement**, demandés un par un.
3. **Écriture** : marchés, sélections et relevés horodatés. Une rencontre
   `1xBet` déjà liée réutilise son lien ; un événement déplacé désactive
   l'ancien lien puis crée le nouveau, dans cet ordre (index « un seul lien
   actif par rencontre »).

Bornes choisies, toutes visibles dans l'interface :

| Borne | Valeur | Raison |
|---|---|---|
| Fenêtre des marchés étendus | 72 heures | une cote de marché secondaire est utile près du coup d'envoi |
| Plafond étendu | 30 événements **par passe**, partagé entre les sept compétitions | empêche une passe de vider le quota |
| Espacement des appels | 0,5 seconde | aucune rafale chez le fournisseur |
| Budget local | 400 crédits par mois | le compte réel en compte 492 |

Le fournisseur **refuse** quatre marchés en un seul appel (`h2h,totals,
double_chance,btts` → 422) : d'où la séparation 2 crédits/compétition puis
2 crédits/événement. Aucune cote n'est dérivée d'une autre.

#### Mesures réelles

Aperçu gratuit du 17/11 sur les sept compétitions : **122 événements,
118 rattachés (96,7 %), 0 ambigu, 4 sans rencontre, 18 crédits estimés**.

Trois passes payantes bornées ont ensuite été exécutées :

| Passe | Crédits | Résultat |
|---|---|---|
| `ligue1` | 2 | 18 liens, 36 marchés, 90 relevés |
| `mls` (2 événements étendus) | 6 | 8 liens, 20 marchés, 50 relevés |
| `ligue1` rejouée | 2 | **0 marché écrit**, 18 liens réutilisés, 90 relevés de plus |

Total : **10 crédits**, quota fournisseur 478/492. Contrôles en base :
56 marchés, 230 relevés, 26 liens actifs, **0 doublon** de `(rencontre,
signature)`, **0** marché marqué manuel, toutes les cotes `source =
the_odds_api` et `bookmaker = 1xBet`, prix dans les bornes 1,01–1 000.

Le rejeu ne duplique aucun marché ni aucun lien ; il ajoute en revanche des
relevés, car la cote du fournisseur a changé entre les deux passes. C'est le
comportement voulu : l'historique est **append-only**, une cote passée n'est
jamais réécrite.

#### Deux corrections nées de la mesure

- `&` et `and` désignent le même connecteur : `Brighton & Hove Albion` (base)
  et `Brighton and Hove Albion` (marché) sont désormais une seule identité.
  Les deux événements Brighton sont passés de « sans rencontre » à rattachés.
- Le plafond de 30 événements étendus est **global à la passe** : il est
  décrémenté par compétition, sinon sept compétitions auraient pu demander
  210 appels payants en une fois.

#### Ce qui reste volontairement non rattaché

`1. FC Köln` / `FC Cologne`, `Sporting Lisbon` / `Sporting Clube de Portugal`,
`AEK Athens` : trois exonymes. Les deviner reviendrait à coder des alias en
dur, ce qui créerait un jour une erreur silencieuse. Ils restent affichés
« sans rencontre » dans le panneau, sans cote, et rattachables à la main.
`Como – AEK` n'a aucun candidat : dans la base, Como joue en Serie A.

#### Contrôles de sortie

`pytest` **301 tests verts**, `ruff` vert, `mypy app engine` vert (95
fichiers), `eslint` et `tsc --noEmit` verts, `next build` réussi après
suppression du cache `.next`. Les 29 tests de `test_odds_sync.py` couvrent le
matcher pur, les 16 décisions réelles figées, le service avec client factice
(aucun appel réseau) et les quatre routes.

#### Reste à faire sur l'étape 4

- **Rien de bloquant.** Les six autres compétitions seront importées à la
  demande depuis l'interface, dans le même budget.
- Les alias d'exonymes restent une décision d'utilisateur, pas une heuristique.


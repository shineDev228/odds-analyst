# Phase 15 — Reconstruction sur BigBallsData

> **Statut : étape 1 livrée le 15/11/2026. Étape 2 à venir.**
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
pour départager les matchs simultanés, puis marge minimale de 0,10.

Mesuré le 15/11/2026 sur 38 événements réels (Ligue 1 + Liga) :

| Résultat | Nombre |
|---|---|
| Rattachés automatiquement | **38 / 38** |
| Marge minimale observée | 0,60 |
| Marge médiane | 1,00 |
| Orientation domicile/extérieur correcte | 38 / 38 |

Cas les plus difficiles, tous résolus : `Rennes` → `Stade Rennais` (0,76),
`Athletic Bilbao` → `Athletic Club` (0,86), `CA Osasuna` → `Osasuna` (0,91).

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
| **3** | Reconstruction réelle : 7 compétitions, ≈ 1 000 requêtes | 972 résultats, 0 doublon, 0 équipe hors BigBallsData |
| **4** | Appariement des cotes par clé composite | les 38 cas mesurés rejoués en test |
| **5** | Enrichissement CSV : xG et cotes de clôture | 209 lignes traitées, 208 automatiques, 1 décision |
| **6** | Page Synchronisation (remplace Connecteurs) + CLI | passe manuelle rejouable |
| **7** | Vérification et documentation d'exploitation | comptages, intégrité, moteur et interface inchangés |

### 5.1 Budget de requêtes

| Passe | Requêtes |
|---|---|
| Reconstruction initiale (7 compétitions) | ≈ 1 000 |
| Statistiques des 972 rencontres | 972 |
| Passe quotidienne (résultats + nouveaux matchs) | ≈ 45 |

Quota : 2 000 par jour, 100 par minute. La reconstruction tient en deux
séances d'une dizaine de minutes.

---

## 6. Risques et parades

| Risque | Probabilité | Effet | Parade |
|---|---|---|---|
| Perte des xG pour les ligues sans CSV | moyenne | moteur au niveau « tirs cadrés » | assumé et affiché ; le moteur bascule automatiquement |
| Deux matchs même jour, même score | moyenne | xG sur le mauvais match | marge de 0,25, sinon aucune écriture |
| Match de coupe dans un flux de championnat | certaine | une rencontre sans xG | toléré, compté dans le rapport de passe |
| Relevé The Odds API indisponible | moyenne | combinaisons sans cote | passe marquée `partial`, jamais de cote inventée |
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
| Appariement | les 209 lignes CSV mesurées : 208 automatiques, 1 en attente |
| Appariement | deux candidats à moins de 0,25 d'écart → aucune écriture, ligne journalisée |
| Import | rejeu immédiat d'une passe → aucune ligne créée, aucun doublon |
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

# Phase 2 — Marchés et cotes

> **Statut : livrée et vérifiée.** Catalogue de 217 modèles (dont 109 pour le
> football), API et interface testées sur une rencontre réelle, 57 tests verts.

## Objectif

Permettre la saisie, l'historisation et l'analyse des cotes 1xBet pour toutes les
familles de marchés, sans scraping ni identifiant de bookmaker.

Le point central est un **modèle universel** : un marché est décrit par une
famille, une période, un sujet (match, équipe ou joueur), une ligne éventuelle et
des sélections. Ce modèle couvre aussi bien le 1X2 que le score exact, les
corners, les cartons, les marchés joueurs ou les marchés de seconde mi-temps.

## Décisions techniques

### 1. Catalogue extensible plutôt qu'énumération figée

1xBet propose des centaines de variantes par rencontre. Les figer dans le code
serait impossible à maintenir. Nous stockons donc :

- un **catalogue** de modèles de marchés (code, famille, sujet, ligne, sélections
  par défaut) pour les marchés courants ;
- la possibilité de créer un **marché personnalisé** pour toute variante non
  cataloguée.

Aucune migration n'est nécessaire pour ajouter un marché 1xBet absent du
catalogue : l'utilisateur le saisit librement.

### 2. Structure normalisée

- `markets` : rencontre, code catalogue, famille, période, sujet, ligne(s).
- `selections` : issues du marché (1, X, 2, Plus, Moins, Oui, Non, score exact…).
- `odds_snapshots` : historique **append-only** des cotes, avec horodatage,
  bookmaker et source.

Chaque relevé de cote crée une ligne : une cote n'est jamais écrasée, ce qui
permettra l'analyse de dérive et la comparaison au modèle statistique.

### 3. Calculs statistiques dans le moteur pur

`engine/odds.py` contient les fonctions pures :

- probabilité implicite d'une cote décimale ;
- marge du bookmaker (overround) ;
- probabilités et cotes équitables normalisées.

Aucun import SQLAlchemy/FastAPI dans ce module.

### 4. Périodes et sujets libres mais validés

Les périodes sont des codes courts (`match`, `mi_temps`, `seconde_mi_temps`,
`prolongation`, `tirs_au_but`, `periode_1`, …). Les sujets sont `match`,
`team` ou `player`. Cela couvre les marchés 1xBet de tous les sports sans
schéma spécifique.

### 5. Saisie manuelle uniquement

Conformément au cahier des charges : aucune connexion à 1xBet, aucun scraping,
aucun identifiant stocké. La source est tracée (`manuel`), et les connecteurs
API autorisés arriveront en Phase 7.

## Périmètre livré

- Catalogue football couvrant les grandes familles 1xBet : résultat, double
  chance, mi-temps, handicaps, totaux de buts, BTTS, scores exacts, marges,
  périodes, corners, cartons, tirs, statistiques d'équipe, marchés joueurs et
  combinés.
- Catalogue des marchés principaux pour tennis, basket, hockey, handball, rugby,
  volley-ball, baseball et esport.
- Création de marchés personnalisés pour tout autre marché 1xBet.
- Saisie des cotes, mise à jour par nouveau relevé, historique.
- Affichage des probabilités implicites, de la marge et des cotes équitables.
- API et interface intégrées à la fiche rencontre.

## Risques et parades

| Risque | Parade |
|---|---|
| Explosion du nombre de marchés | Modèle universel + catalogue + marchés personnalisés |
| Doublons de marchés | Signature normalisée unique par rencontre |
| Cotes erronées | Validation `> 1`, historique append-only, suppression d'un relevé erroné auditée |
| Confusion période / sujet | Champs explicites affichés dans l'interface |
| Dépendance à 1xBet | Aucune : saisie manuelle, modèle indépendant du bookmaker |
| Volume de données | Index sur rencontre, sélection et date de relevé |

## Tests prévus

### Moteur
- Probabilité implicite, marge, cotes équitables.
- Cas limites : cote ≤ 1 refusée, marché incomplet.

### API
- Catalogue disponible et idempotent.
- Création d'un marché catalogué avec sélections et cotes.
- Rejet des doublons (même code, période, sujet, ligne).
- Rejet d'un sujet équipe étranger à la rencontre.
- Ajout d'un nouveau relevé sans écraser l'ancien.
- Calcul de la marge et des probabilités dans la réponse.
- Suppression d'un marché et de son historique.
- Marché personnalisé accepté.
- Contrôle d'accès et CSRF.

### Interface
- Parcours réel : ajout d'un 1X2, d'un total de buts et d'un marché joueur,
  mise à jour d'une cote, vérification de l'historique et de la marge.

## Critères d'acceptation

1. ✅ Un marché 1X2 avec trois cotes affiche une marge cohérente.
2. ✅ L'ajout d'une cote crée un nouveau relevé horodaté.
3. ✅ Un marché personnalisé est accepté sans migration.
4. ✅ Les marchés sont visibles sur la fiche de la rencontre.
5. ✅ Aucune régression sur les 34 tests de la Phase 1.
6. ✅ `ruff`, `mypy`, `pytest`, `eslint`, `tsc` et `next build` passent.

## Vérification manuelle

Parcours réalisé dans le navigateur : ajout d'un 1X2 (2,00 / 3,50 / 4,20),
mise à jour d'une cote (1,95 puis retour à 2,00), contrôle de l'historique,
ajout d'un total de buts (ligne 2,5) et d'un marché joueur, puis suppression
d'un relevé et d'un marché. La marge, les probabilités implicites et les cotes
équitables sont recalculées à chaque relevé.

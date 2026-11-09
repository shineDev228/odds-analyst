# Phase 5 — Historique et performance

> **Statut : validée.** Enregistrement des
> combinaisons générées, règlement automatique des sélections et mesure de
> performance, sans recommandation de mise.

## Objectif

Permettre d'**enregistrer une combinaison générée en Phase 4**, puis de suivre
son sort une fois les rencontres terminées :

- statut de chaque sélection (gagnée, perdue, remboursée, en attente,
  indisponible) ;
- statut de la combinaison (gagnée, perdue, remboursée, en attente,
  indisponible) ;
- cote effective, gain ou perte exprimés en **unités de mise** (1 unité par
  combinaison enregistrée) ;
- synthèse de performance : nombre de combinaisons, taux de réussite, unités
  engagées, unités retournées, résultat net, ROI et cote moyenne.

L'historique est un **outil de mesure**, pas un conseil de pari. Les résultats
passés ne préjugent pas des résultats futurs et un petit échantillon ne prouve
rien.

## Périmètre v1

- Enregistrement manuel d'une combinaison issue du générateur football.
- Marchés réglables : **1X2**, **double chance** et **plus / moins de buts**
  (lignes demi-entitères ou entières).
- Règlement calculé à partir du statut et du score **actuels** de la rencontre.
- Une seule sélection par rencontre, comme à la génération.
- Suppression manuelle d'une combinaison enregistrée.

## Hors périmètre (phases suivantes)

- Placement automatique de paris, cash-out, bankroll et gestion de mise
  réelle : jamais.
- Autres sports et marchés non couverts par le modèle v1 (Phase 6/7).
- Règlement manuel d'un marché exotique ou d'un score exact (Phase 6/7).
- Calibration statistique avancée du modèle (Phase 6).
- Import automatique de résultats (Phase 7).

## Décisions techniques

### 1. Instantané immuable de la combinaison

Une combinaison enregistrée ne dépend pas de l'état futur des marchés. Chaque
sélection est copiée dans une table de jambes avec :

- la rencontre, la compétition et l'heure de coup d'envoi ;
- le marché, sa famille, sa période et sa ligne ;
- le code et le libellé de la sélection ;
- la cote, la probabilité estimée et sa fourchette au moment de
  l'enregistrement.

Les liens vers la rencontre, le marché et la sélection sont facultatifs
(`ON DELETE SET NULL`) : si une donnée est supprimée, l'historique reste lisible
mais la jambe devient **indisponible** au règlement.

### 2. Règlement dérivé, jamais stocké

Le statut n'est pas figé en base. Il est recalculé à chaque lecture à partir
des données de la rencontre. Avantages :

- une correction de score se répercute immédiatement ;
- aucun statut obsolète ni tâche de fond ;
- le calcul reste déterministe et testable.

Le calcul vit dans le moteur pur `apps/api/engine/settlement/`, sans accès à la
base ni à FastAPI. Les services se contentent de fournir les scores et les
règles.

### 3. Règles de règlement

| Marché | Règle |
|---|---|
| 1X2 | `1` si domicile gagne, `X` si égalité, `2` si extérieur gagne |
| Double chance | `1X`, `12`, `X2` selon le résultat final |
| Plus / moins | total des buts comparé à la ligne ; égalité = remboursé |

Statuts d'une jambe :

- **en attente** : rencontre programmée ou en cours ;
- **gagnée** / **perdue** : rencontre terminée avec score et règle reconnue ;
- **remboursée** : rencontre reportée ou annulée, ou total égal à la ligne ;
- **indisponible** : marché non réglable, règle absente ou score manquant.

Statuts d'une combinaison, par ordre de priorité :

1. **perdue** dès qu'une jambe est perdue ;
2. **indisponible** si aucune jambe n'est perdue mais qu'au moins une est
   indisponible ;
3. **en attente** si aucune jambe n'est perdue ni indisponible et qu'au moins
   une attend ;
4. **remboursée** si toutes les jambes sont remboursées ;
5. **gagnée** si toutes les jambes sont gagnées ou remboursées, avec une cote
   effective recalculée sans les jambes remboursées.

### 4. Performance en unités, pas en argent

Chaque combinaison réglée compte pour **1 unité engagée** :

```
unités retournées = cote effective (si gagnée) ou 1 (si remboursée)
résultat net      = unités retournées − unités engagées
ROI               = résultat net / unités engagées
taux de réussite  = gagnées / (gagnées + perdues)
```

Les combinaisons en attente ou indisponibles sont exclues du dénominateur. Le
taux de réussite exclut les remboursements, qui ne sont ni des succès ni des
échecs. Aucun montant en euros n'est demandé ni affiché.

### 5. Validation serveur à l'enregistrement

Le serveur ne fait pas confiance au navigateur :

- chaque sélection doit exister et appartenir à la rencontre annoncée ;
- la cote fournie doit correspondre à un relevé de cote réellement stocké ;
- la rencontre doit être à venir au moment de l'enregistrement ;
- le marché doit être `match`, de période `match`, et réglable par la v1 ;
- les rencontres doivent être distinctes ;
- la probabilité, la fourchette, la cote totale et l'espérance sont
  recalculées côté serveur ;
- une empreinte empêche d'enregistrer deux fois exactement la même combinaison
  (mêmes sélections, mêmes cotes).

### 6. API et pagination

Le statut étant dérivé, le filtrage par statut se fait après calcul. Pour
l'usage personnel visé, l'API charge au plus quelques centaines de
combinaisons, puis pagine en mémoire. Ce compromis est documenté et testé ; il
pourra être remplacé par une vue SQL si le volume augmente.

## Modèle de données

Deux tables additives, sans modification destructive des tables existantes.

### `saved_combinations`

| Colonne | Type | Contrainte |
|---|---|---|
| `id` | UUID | clé primaire |
| `user_id` | UUID | FK `users`, suppression en cascade |
| `nombre_selections` | entier | entre 2 et 15 |
| `cote_min`, `cote_max` | flottants | `> 1`, min < max |
| `marches_autorises` | JSON | liste de codes |
| `total_odds` | flottant | `> 1` |
| `probability`, `low`, `high` | flottants | entre 0 et 1 |
| `expected_value` | flottant | — |
| `fingerprint` | chaîne | unique par utilisateur |
| `note` | chaîne | facultative |
| `created_at`, `updated_at` | dates | — |

### `saved_combination_legs`

| Colonne | Type | Contrainte |
|---|---|---|
| `id` | UUID | clé primaire |
| `combination_id` | UUID | FK `saved_combinations`, cascade |
| `position` | entier | ordre d'affichage |
| `match_id`, `market_id`, `selection_id` | UUID | FK, `SET NULL` |
| `match_label`, `competition_name` | chaînes | instantané |
| `kickoff_at` | date | instantané |
| `market_name`, `market_family`, `market_period` | chaînes | instantané |
| `selection_code`, `selection_label` | chaînes | instantané |
| `line` | flottant | facultatif |
| `decimal_odds` | flottant | `> 1` |
| `probability`, `low`, `high` | flottants | entre 0 et 1 |

Contraintes : position unique par combinaison, une seule jambe par rencontre,
et index sur `combination_id`, `match_id` et `created_at`.

## API

| Méthode | Route | Rôle |
|---|---|---|
| `POST` | `/combinations` | Enregistrer une combinaison |
| `GET` | `/combinations` | Lister l'historique paginé |
| `GET` | `/combinations/performance` | Synthèse de performance |
| `GET` | `/combinations/{id}` | Détail et règlement |
| `DELETE` | `/combinations/{id}` | Supprimer une combinaison |

`POST /combinations` reçoit les sélections avec `match_id`, `selection_id` et
`decimal_odds`, ainsi que les paramètres de génération et une note facultative.
La réponse contient la combinaison enregistrée avec son règlement.

`GET /combinations` accepte `page`, `page_size` et `statut` (`toutes`,
`en_attente`, `gagnee`, `perdue`, `remboursee`, `indisponible`). Chaque entrée
expose les jambes avec leur statut, le score éventuel et la cote effective.

`GET /combinations/performance` renvoie :

- le nombre total de combinaisons et la répartition par statut ;
- le taux de réussite et la cote moyenne des combinaisons réglées ;
- les unités engagées, retournées, le résultat net et le ROI ;
- un avertissement sur la taille de l'échantillon.

### Évolution de la Phase 4

`POST /combinations/generate` ajoute `market_id` et `selection_id` à chaque
sélection retournée. Ces identifiants sont nécessaires pour enregistrer une
combinaison sans reconstruire les correspondances côté navigateur.

## Interface

- Nouvelle entrée **Historique** dans la navigation latérale.
- Bouton **Enregistrer** sur chaque combinaison générée, avec confirmation et
  lien vers l'historique.
- Page Historique :
  - indicateurs de synthèse (total, réglées, gagnées, perdues, en attente,
    taux de réussite, unités, résultat net, ROI) ;
  - filtres par statut ;
  - cartes de combinaisons avec cote totale, cote effective, statut, date,
    jambes et statut de chaque jambe ;
  - score de la rencontre lorsqu'il est disponible ;
  - suppression avec confirmation ;
  - état vide et avertissement permanent sur l'incertitude.
- Aucune formulation certaine, aucune recommandation de mise.

## Risques et parades

| Risque | Parade |
|---|---|
| Cotes inventées par le client | Vérification contre un relevé stocké, recalcul serveur |
| Double enregistrement | Empreinte unique par utilisateur, réponse `409` |
| Historique faussé par une correction de score | Règlement dérivé et recalculé, mention explicite |
| Rencontre ou sélection supprimée | Jambe `indisponible`, comptée séparément |
| Petit échantillon présenté comme preuve | Taille affichée, avertissement, pas de conclusion |
| Confusion unités / argent | Unités uniquement, aucun montant, aucun conseil |
| Performance filtrée en mémoire | Volume plafonné et documenté, pagination testée |
| Migration risquée | Tables additives uniquement, aucune colonne existante modifiée |
| Fuseaux horaires | Normalisation UTC comme dans les phases précédentes |

## Tests prévus

### Moteur de règlement
- 1X2 : victoire domicile, nul, victoire extérieur.
- Double chance : les trois combinaisons.
- Plus / moins : au-dessus, en dessous, égalité remboursée.
- Rencontre programmée, en cours, reportée, annulée.
- Score manquant ou marché inconnu : indisponible.
- Priorité perdue > indisponible > en attente > remboursée > gagnée.
- Cote effective recalculée sans les jambes remboursées.
- Gain, perte et remboursement en unités.

### API
- Authentification et CSRF requis.
- Enregistrement valide, avec cote et probabilité recalculées.
- Rejet d'une rencontre en double, d'une sélection inconnue, d'une cote non
  stockée, d'une rencontre déjà commencée et d'un marché non réglable.
- Rejet du doublon par empreinte.
- Liste, filtres, pagination, détail et suppression.
- Règlement mis à jour après saisie du score.
- Synthèse cohérente avec les combinaisons détaillées.
- Cotes figées : un nouveau relevé ne modifie pas une combinaison enregistrée.
- Suppression d'une rencontre : jambe indisponible, pas d'erreur serveur.

### Interface
- Enregistrement depuis la page Combinaisons.
- Page Historique, filtres, indicateurs et états vides.
- Affichage des statuts, scores et cotes effectives.
- Suppression avec confirmation.
- Avertissements visibles, aucune promesse de gain.

## Critères d'acceptation

1. Une combinaison générée peut être enregistrée puis retrouvée dans
   l'historique.
2. Une cote inventée, une rencontre déjà commencée ou un doublon sont refusés
   avec un message explicite.
3. Le règlement est correct pour 1X2, double chance et plus / moins.
4. Les statuts en attente, remboursé et indisponible sont distingués.
5. La synthèse de performance est cohérente avec le détail et indique la taille
   de l'échantillon.
6. Les cotes enregistrées ne changent pas lorsqu'un nouveau relevé est saisi.
7. L'interface permet d'enregistrer, consulter, filtrer et supprimer.
8. `ruff`, `mypy`, `pytest`, `eslint`, `tsc` et `next build` passent.

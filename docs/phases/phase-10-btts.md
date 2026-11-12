# Phase 10 — Marché « les deux équipes marquent »

> **Statut : validée le 11 novembre 2026.**
>
> Cette phase branche le marché « Les deux équipes marquent » (BTTS) dans le
> générateur de combinaisons et dans le règlement automatique de l'historique.
> Le moteur statistique ne change pas : les probabilités et les fourchettes
> existaient déjà, elles sont seulement réutilisées.

## Objectifs

1. Permettre au générateur de proposer des sélections « Oui » / « Non » sur le
   marché « Les deux équipes marquent ».
2. Régler automatiquement ces sélections dans l'historique, sans ambiguïté.
3. Réutiliser les probabilités du modèle et leur fourchette à 80 % : aucune
   nouvelle estimation, aucun nouveau calcul.
4. Activer les quatre marchés par défaut, tout en laissant le BTTS décochable.
5. Ne pas dégrader la vitesse de génération ni les fonctionnalités existantes.

## Décisions techniques

| Décision | Justification |
|---|---|
| Famille `btts`, codes `oui` / `non` | Les codes correspondent déjà à ceux du catalogue de marchés et de l'import The Odds API. |
| Probabilité issue de `prediction.btts` | Le modèle estime déjà `btts_yes` et `btts_no`, fourchette à 80 % comprise : rien n'est inventé côté service. |
| Aucun changement du moteur statistique | Le besoin est un branchement, pas une nouvelle méthode. La simulation Monte-Carlo n'est pas rouverte. |
| Règlement sans remboursement | Sur ce marché, il n'existe pas de « push » : « Oui » gagne si les deux équipes marquent, « Non » sinon. |
| Score absent → indisponible | Un score incomplet ne permet pas de trancher ; mieux vaut une sélection indisponible qu'un statut faux. |
| Rencontre reportée ou annulée → remboursée | Règle déjà appliquée aux autres marchés, reprise telle quelle. |
| Quatre marchés cochés par défaut | Décision utilisateur : le BTTS est proposé d'office, mais reste décochable dans les critères et les paramètres. |
| Aucune migration de schéma | La famille est stockée dans les colonnes existantes (`market_family`, `selection_code`). |

## Implémentation

### Générateur

`apps/api/app/services/combinations.py`

- `MARKET_FAMILIES` gagne `"BTTS": ("btts",)`.
- `model_selection` reconnaît la famille `btts`, la période `match` et les codes
  `oui` / `non`, puis renvoie la probabilité et la fourchette de
  `prediction.btts`.
- Une sélection BTTS sans cote récente est ignorée comme les autres : le
  générateur n'utilise que des cotes saisies ou importées.

`apps/api/app/schemas/combination.py`

- `ALLOWED_MARKETS` passe à quatre entrées.
- `marches_autorises` accepte jusqu'à quatre valeurs ; un cinquième marché, un
  marché inconnu ou une liste vide restent refusés (erreur 422).

`apps/api/app/schemas/settings.py` et `apps/api/app/db/seed.py`

- Les préférences par défaut contiennent les quatre marchés.

### Règlement

`apps/api/engine/settlement/__init__.py`

- `SUPPORTED_FAMILIES["btts"] = {"oui", "non"}`.
- Nouvelle `_settle_btts` : `both_scored = home_score > 0 and away_score > 0`.
  « Oui » gagne si `both_scored`, « Non » gagne sinon.
- Aucun remboursement sur ce marché : seuls un score manquant (indisponible) ou
  une rencontre reportée/annulée (remboursée) sortent de cette règle.
- Les messages « modèle v1 » deviennent « modèle statistique ».

`apps/api/app/services/history.py`

- `MARKET_FAMILIES_BY_CODE["BTTS"] = "btts"` et
  `SUPPORTED_CODES["btts"] = {"oui", "non"}` : une combinaison contenant du BTTS
  peut être enregistrée et recalculée.
- Un marché non réglable (corners, cartons, joueurs…) reste refusé à
  l'enregistrement.

### Interface

`apps/web/src/app/(app)/combinaisons/page.tsx` et
`apps/web/src/app/(app)/parametres/page.tsx`

- Case à cocher « Les deux équipes marquent », active par défaut, décochable.

### Données

Aucune migration de schéma. Sur une base existante, la préférence
`marches_autorises` déjà enregistrée ne bénéficie pas automatiquement des
nouvelles valeurs par défaut : elle a été complétée par `BTTS` en conservant
les autres valeurs, pour que le marché soit réellement coché par défaut. Les
nouvelles installations reçoivent directement les quatre marchés.

## Règles de règlement

| Score | « Oui » | « Non » |
|---|---|---|
| 0-0 | Perdue | Gagnée |
| 1-0 | Perdue | Gagnée |
| 1-1 | Gagnée | Perdue |
| 4-3 | Gagnée | Perdue |
| Score absent | Indisponible | Indisponible |
| Rencontre reportée | Remboursée | Remboursée |

## Tests

| Fichier | Couverture |
|---|---|
| `apps/api/tests/test_combinations.py` | BTTS seul, BTTS ignoré quand il n'est pas autorisé, quatre marchés acceptés, cinquième marché et marché inconnu refusés, fourchettes présentes |
| `apps/api/tests/test_settlement_engine.py` | Règlement sur 0-0, 1-0, 1-1, 4-3, score absent, rencontre reportée, marché inconnu |
| `apps/api/tests/test_history.py` | Enregistrement d'une combinaison BTTS puis règlement après saisie des scores ; corners toujours refusés à l'enregistrement |
| `apps/api/tests/test_settings.py` | Les quatre marchés sont présents par défaut |

Résultat : **254 tests** (241 existants + 13 nouveaux), `ruff` et `mypy` sans
erreur ; `eslint`, `tsc` et compilation de production Next.js sans erreur.

## Performance

Mesure sur la copie de vérification (9 rencontres cotées, 207 rencontres
programmées) :

| Étape | Avant | Après |
|---|---|---|
| Génération complète | 0,91 s | 0,83 s |
| Seconde génération | — | 0,64 s |

La variation est dans le bruit de mesure ; le seuil de 2 secondes reste
respecté. Le nombre de candidats augmente, mais les rencontres sans cote sont
toujours écartées avant calcul.

## Vérification de bout en bout

Sur la copie `odds_analyst_restore_test`, deux rencontres cotées ont reçu un
marché BTTS temporaire :

- génération avec le seul marché BTTS : 2 rencontres exploitables,
  4 sélections, 4 combinaisons ;
- probabilités et fourchettes réelles affichées (par exemple 0,5178
  [0,3340 ; 0,7128] pour « Oui ») ;
- marché temporaire supprimé après vérification, aucun BTTS restant.

La base réelle n'a pas été modifiée par cette vérification.

## Risques et parades

| Risque | Parade |
|---|---|
| Explosion combinatoire avec un quatrième marché | Mesure avant/après ; rencontres sans cote écartées avant calcul ; limite de 50 rencontres |
| Règlement ambigu sur les scores limites | Tests explicites 0-0, 1-0, 1-1, 4-3 ; score absent → indisponible |
| Probabilité présentée comme certaine | La fourchette à 80 % du modèle est conservée et affichée |
| Documentation devenue fausse | Guide d'utilisation et README mis à jour dans la même livraison |
| Régression sur les trois marchés existants | 241 tests conservés, 13 ajoutés ; CI verte |

## Ce que cette phase ne fait pas

- Aucun changement du modèle statistique ni de la simulation d'incertitude.
- Aucune nouvelle ligne de totaux : le générateur reste limité à 1,5 / 2,5 / 3,5.
- Aucun autre marché (corners, cartons, joueurs, mi-temps) dans le générateur.
- Aucune migration de base de données.
- Aucun placement automatique de pari, aucun scraping non autorisé.
- Aucune combinaison présentée comme certaine : la fourchette d'incertitude
  reste affichée.

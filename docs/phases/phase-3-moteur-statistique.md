# Phase 3 — Moteur statistique v1

> **Statut : implémentée — en attente de validation.** Modèle football fondé sur
> les buts, avec fourchettes d'incertitude obligatoires.

## Objectif

Produire, pour une rencontre de football, des **probabilités estimées** sur les
marchés principaux (1X2, double chance, totaux de buts, les deux équipes
marquent, scores exacts), à partir de l'historique de résultats saisi.

Le moteur ne prédit pas un résultat : il estime une distribution de scores et
affiche systématiquement une fourchette d'incertitude. Aucune sortie ne doit
être présentée comme certaine.

## Hors périmètre (phases suivantes)

- Combinaisons de paris et filtres de cotes (Phase 4).
- Historique de performance et calibration (Phase 5).
- Modèle v2 : xG, compositions, blessures, force du championnat (Phase 6).
- Sports autres que le football : le moteur v1 est spécifique au football.
- Apprentissage automatique : aucune dépendance à un service payant.

## Décisions techniques

### 1. Modèle multiplicatif de forces + Poisson bivarié

Chaque équipe reçoit une force d'attaque et une force de défense relatives à
la moyenne du championnat. Les buts attendus sont :

```
λ_domicile = moyenne_buts × attaque_domicile × défense_extérieur × facteur_domicile
λ_extérieur = moyenne_buts × attaque_extérieur × défense_domicile × facteur_extérieur
```

La distribution des scores suit une loi de Poisson bivariée, avec la
**correction Dixon-Coles** sur les scores faibles (0-0, 1-0, 0-1, 1-1), qui
corrige la sous-estimation des matchs fermés.

### 2. Pondération temporelle et régularisation

- Chaque match est pondéré par demi-vie : `0,5 ^ (jours / demi_vie)`.
- La demi-vie (240 jours par défaut) et le nombre de matchs (38 par défaut)
  viennent des préférences existantes.
- Les forces sont **régularisées** vers la moyenne (prior de 5 matchs) pour
  éviter qu'un petit échantillon produise des probabilités extrêmes.
- L'avantage du terrain est estimé sur les données, puis régularisé vers un
  prior de 1,12 / 0,90.

### 3. Incertitude par simulation Monte Carlo

Les forces estimées sont incertaines. Le moteur simule 1 000 tirages des
forces (loi log-normale dont l'écart-type dépend de l'échantillon effectif),
recalcule la matrice des scores et les probabilités, puis restitue les
percentiles 10 et 90.

- Le tirage est **déterministe** (graine fixe) : un même historique produit les
  mêmes fourchettes.
- Une fourchette large signale un historique faible ; elle ne doit jamais être
  masquée.
- L'échantillon effectif tient compte des poids : `(Σw)² / Σw²`.

### 4. Moteur pur, service mince

- `apps/api/engine/` reste sans SQLAlchemy, FastAPI, HTTP ni lecture de fichier.
- `app/services/predictions.py` charge l'historique, applique les préférences et
  sérialise le résultat.
- La route `GET /matches/{id}/prediction` ne fait qu'orchestrer.

### 5. Garde-fous de données

- Seuls les matchs **terminés**, avec scores, et **antérieurs au coup d'envoi**
  sont utilisés.
- Minimum 3 matchs terminés par équipe ; sinon `409` avec un message explicite.
- Les avertissements de qualité sont affichés : échantillon réduit, absence de
  match récent, historique toutes compétitions, modèle v1 fondé sur les buts.

## Formules et unités

- Probabilités entre 0 et 1, affichées en pourcentage.
- Buts attendus (`xG modèle`) en buts par match.
- Marge d'incertitude exprimée en points de probabilité (percentiles 10–90).
- Toute probabilité est bornée et les fourchettes sont élargies pour contenir
  l'estimation centrale.

## Risques et parades

| Risque | Parade |
|---|---|
| Surconfiance sur petit échantillon | Régularisation + fourchettes larges + niveau de fiabilité affiché |
| Historique incomplet | Minimum de matchs, avertissements explicites, refus si insuffisant |
| Mélange de compétitions | Avertissement « historique toutes compétitions » |
| Données obsolètes | Pondération par demi-vie + avertissement si dernier match ancien |
| Mauvais calibrage | Modèle volontairement simple et mesurable ; calibration en Phase 5 |
| Présentation trompeuse | Libellé « probabilité estimée », fourchette obligatoire, avertissement permanent |
| Déterminisme | Graine fixe et tests de reproductibilité |

## Tests prévus

### Moteur
- Matrice des scores : somme = 1, marginales cohérentes.
- 1X2 : somme = 1 ; double chance = combinaisons exactes.
- Totaux : plus/moins complémentaires ; ligne entière avec push.
- BTTS : oui/non complémentaires.
- Dixon-Coles : effet sur les scores faibles et normalisation.
- Forces : une attaque plus forte augmente les buts attendus.
- Pondération : un match récent pèse plus qu'un match ancien.
- Incertitude : `low ≤ estimation ≤ high`, reproductibilité, réduction avec
  plus de données.
- Données insuffisantes : exception explicite.

### API
- Accès authentifié requis.
- `409` si historique insuffisant, message en français.
- Réponse cohérente : probabilités dans [0, 1], sommes à 1, fourchettes
  ordonnées, buts attendus positifs.
- Les matchs futurs et non terminés sont ignorés.
- Les préférences (demi-vie, nombre de matchs) sont appliquées.

### Interface
- Panneau « Analyse statistique » sur la fiche rencontre.
- Affichage du niveau de fiabilité, des avertissements, des xG et des
  fourchettes.
- État explicite quand l'historique est insuffisant.
- Aucune formulation certaine.

## Critères d'acceptation

1. Une rencontre avec un historique suffisant affiche des probabilités 1X2 dont
   la somme vaut 100 % (aux arrondis d'affichage près).
2. Chaque probabilité est accompagnée d'une fourchette basse/haute.
3. Une rencontre sans historique suffisant renvoie un message clair, pas une
   probabilité inventée.
4. Les fourchettes se resserrent quand l'historique augmente.
5. Le moteur reste pur (aucun import applicatif) et tous les tests passent.
6. `ruff`, `mypy`, `pytest`, `eslint`, `tsc` et `next build` passent.

# Phase 6 — Moteur statistique v2

> **Statut : implémentée — en attente de validation.** Intégration des
> statistiques de tirs et de xG, estimation régularisée du paramètre
> Dixon-Coles et mesure rétrospective de la calibration du modèle.

## Objectif

Améliorer le moteur football de la Phase 3 sur trois axes mesurables, sans
ajouter de service payant ni de source de données externe :

1. **Exploiter les statistiques déjà saisies** : les buts attendus (xG) et, à
   défaut, les tirs cadrés, afin de réduire le bruit des résultats uniquement
   basés sur les buts.
2. **Estimer le paramètre Dixon-Coles `rho`** à partir des résultats observés,
   au lieu de le fixer à `-0,05`, avec une régularisation forte pour les petits
   échantillons.
3. **Mesurer la calibration** du modèle par un rétro-test honnête : chaque
   rencontre passée est pronostiquée avec l'historique strictement antérieur à
   son coup d'envoi, puis comparée au résultat réel (score de Brier, log loss,
   compétence par rapport à une base de référence, tableau de fiabilité).

Le moteur continue de produire des **probabilités estimées** avec fourchette
d'incertitude. La calibration est un outil de mesure : elle ne transforme pas
une estimation en certitude et ne garantit aucun résultat futur.

## Périmètre v2

- Football uniquement, comme le moteur v1.
- Intégration de `expected_goals` (xG saisi) et d'un proxy fondé sur
  `shots_on_target` (tirs cadrés).
- Estimation régularisée de `rho` (Dixon-Coles) sur l'historique disponible.
- Rétro-test walk-forward du marché **1X2** : Brier, log loss, précision,
  score de compétence, erreur de calibration (ECE) et tableau de fiabilité par
  tranches de probabilité.
- Version de modèle `football-poisson-v2`, exposée dans l'API et l'interface.
- Traçabilité des sources : nombre de matchs avec xG, avec proxy, ou sans
  statistique, pour chaque équipe.

## Hors périmètre (phases suivantes)

- **Compositions, blessures et suspensions** : aucune source de données fiable
  n'est disponible en saisie manuelle ; ces éléments relèvent des connecteurs
  de la Phase 7.
- **Force du championnat** : l'estimation inter-compétitions exige des
  rencontres entre équipes de niveaux différents ; les connecteurs de la
  Phase 7 apporteront ce volume.
- **Enregistrement des prévisions réelles avant match** (instantanés) : le
  rétro-test est explicitement rétrospectif, sans effet de bord sur un `GET`.
  Un suivi des prévisions réelles pourra être ajouté ultérieurement.
- Autres sports, marchés exotiques et nouveaux marchés de combinaisons.
- Apprentissage automatique, services payants, placement automatique de paris :
  jamais.

## Décisions techniques

### 1. Moteur pur et rétro-compatible

Les ajouts restent dans `apps/api/engine/`, sans SQLAlchemy, FastAPI, HTTP ni
lecture de fichier. Les champs xG sont **facultatifs** dans `HistoricalMatch` :
un appel v1 sans statistiques produit exactement le comportement « buts
uniquement ».

### 2. Intégration du xG et du proxy tirs cadrés

Pour chaque rencontre passée d'une équipe, on construit une valeur de buts
« observée » :

```
si expected_goals est renseigné :        xg = expected_goals
sinon si shots_on_target est renseigné : xg = min(0,30 × tirs_cadrés, 4,0)
sinon :                                  xg = absent

valeur_attaque = (1 − w) × buts_pour + w × xg
valeur_défense = (1 − w) × buts_contre + w × xg_contre
```

- `w = 0,50` par défaut (`xg_weight`), borné entre 0 et 1.
- Si le xG est absent pour une rencontre, cette rencontre utilise les buts
  réels (`w = 0` localement) : aucune valeur n'est inventée.
- Le proxy `0,30 × tirs cadrés` reflète le taux de conversion moyen d'un tir
  cadré ; il est plafonné à 4 buts attendus pour éviter qu'un match aberrant
  domine l'échantillon.
- Les valeurs négatives ou supérieures à 20 sont ignorées (la validation de
  l'API les refuse déjà à la saisie).

La couverture xG est calculée par équipe et pondérée par la demi-vie :

```
couverture = poids des matchs avec xG / poids total des matchs
```

Elle est affichée et déclenche un avertissement si elle est inférieure à 50 %.

### 3. Estimation régularisée de `rho`

Le paramètre `rho` de Dixon-Coles corrige les scores faibles. La v2 l'estime
sur le bassin de rencontres utilisé par le modèle (toutes compétitions du sport
confondues, comme la moyenne de buts actuelle).

1. Calcul des moyennes de buts à domicile et à l'extérieur du bassin, pondérées
   par la demi-vie.
2. Pour chaque valeur candidate `rho` dans `[-0,20 ; +0,15]` (pas de 0,005),
   calcul de la vraisemblance logarithmique pondérée des scores observés sous
   la loi de Poisson bivariée corrigée, puis normalisation sur la grille
   tronquée.
3. Choix du `rho` de vraisemblance maximale, puis **rétrécissement** vers le
   prior `-0,05` :

```
n_eff      = (Σw)² / Σw²
rho_final  = (n_eff × rho_mle + 30 × rho_prior) / (n_eff + 30)
```

- Un historique court reste donc proche du prior ; un historique long laisse
  parler les données.
- `rho_final` est borné à `[-0,20 ; +0,15]` et exposé dans la réponse API.
- L'estimation est globale au bassin (elle n'utilise pas les forces
  individuelles) : c'est un choix volontairement simple, stable et explicable.

### 4. Rétro-test walk-forward sans fuite

Le module pur `engine/calibration/` reçoit une liste d'observations :

```
(probabilités 1X2 estimées, résultat réel, date de coup d'envoi)
```

et calcule :

| Indicateur | Formule |
|---|---|
| Score de Brier | moyenne de `Σ (p_i − o_i)²` sur les trois issues |
| Log loss | `−moyenne(ln(p_réalisée))`, probabilité bornée à `10⁻⁶` |
| Précision | part des rencontres où l'issue la plus probable est réalisée |
| Brier de référence | même score avec les fréquences de base de l'échantillon (1, X, 2) |
| Compétence Brier | `1 − Brier / Brier_référence` (positif = meilleur que la base) |
| ECE | moyenne pondérée de `|probabilité moyenne − fréquence observée|` par tranche |
| Tableau de fiabilité | 10 tranches `[0 ; 0,1[ … [0,9 ; 1]`, effectif, probabilité moyenne, fréquence observée, intervalle de Wilson à 95 % |

- Le service ne sélectionne que des rencontres **terminées**, avec score, et
  reconstruit pour chacune l'historique **strictement antérieur au coup
  d'envoi**. Le résultat de la rencontre cible sert uniquement à l'évaluation.
- Les rencontres sans historique suffisant (moins de 3 matchs terminés par
  équipe avant le coup d'envoi) sont **exclues et comptées**.
- Le calcul utilise uniquement les probabilités ponctuelles : aucune simulation
  Monte Carlo n'est lancée pour le rétro-test, ce qui le rend rapide.
- Le rapport précise la période couverte, le nombre d'exclusions et la
  couverture xG. Un échantillon inférieur à 30 rencontres déclenche un
  avertissement renforcé.

### 5. Séparation prédiction ponctuelle / intervalles

`predict_football` est scindé en deux étapes :

- `predict_point_football` : forces, `rho`, matrice, marchés, qualité ;
- `predict_football` : appelle la précédente puis ajoute les fourchettes Monte
  Carlo avec le `rho` estimé.

Le rétro-test appelle uniquement la première étape. Les sorties et tests v1
restent couverts ; seule la version de modèle change.

## API

| Méthode | Route | Rôle |
|---|---|---|
| `GET` | `/matches/{id}/prediction` | Analyse v2 (version, sources, `rho`) |
| `GET` | `/predictions/calibration?limit=40` | Rétro-test et indicateurs de calibration |

- `limit` est borné entre 10 et 100 (40 par défaut) et désigne le nombre
  maximal de rencontres récentes évaluées.
- La réponse de calibration contient les métriques, les tranches de fiabilité,
  la période, les exclusions, la couverture xG et un avertissement.
- `PredictionRead` gagne des champs **additifs** : `sources` (xG, proxy, buts,
  couverture par équipe) et les paramètres `dixon_coles_rho` / `xg_weight` dans
  `config`. Aucun champ existant n'est supprimé.

### Réponse de calibration (extrait)

```json
{
  "model_version": "football-poisson-v2",
  "matches_evaluated": 40,
  "matches_excluded": 12,
  "brier": 0.58,
  "log_loss": 0.98,
  "accuracy": 0.47,
  "baseline_brier": 0.63,
  "brier_skill": 0.079,
  "ece": 0.041,
  "bins": [
    {
      "low": 0.3,
      "high": 0.4,
      "count": 18,
      "mean_predicted": 0.35,
      "observed": 0.33,
      "wilson_low": 0.16,
      "wilson_high": 0.55
    }
  ],
  "xg_coverage": 0.75,
  "avertissement": "Rétro-test rétrospectif…"
}
```

## Interface

- **Fiche rencontre** : titre « Analyse statistique (modèle v2) », mention des
  sources utilisées (xG, proxy tirs cadrés ou buts seuls) et du `rho` estimé.
  Les avertissements v1 sont remplacés par un message v2 honnête.
- **Nouvelle page « Calibration »** dans la navigation latérale :
  - sélecteur du nombre de rencontres (20, 40, 60, 100) ;
  - indicateurs : rencontres évaluées, Brier, log loss, précision, compétence
    Brier, ECE ;
  - tableau de fiabilité avec effectif, probabilité moyenne, fréquence
    observée, intervalle de Wilson et écart, accompagné de barres simples ;
  - période couverte, exclusions, couverture xG ;
  - avertissements sur la taille de l'échantillon et le caractère rétrospectif ;
  - état vide explicite lorsqu'aucune rencontre n'est évaluable ;
  - aucune conclusion automatique, aucune promesse de gain.
- Responsive, thème sombre et composants existants ; aucune nouvelle
  bibliothèque graphique.

## Risques et parades

| Risque | Parade |
|---|---|
| xG saisi de façon incomplète ou tardive | Couverture affichée, avertissement sous 50 %, repli sur les buts |
| Proxy tirs cadrés trompeur | Pondération 0,30, plafond 4,0, jamais utilisé si absent |
| `rho` instable sur petit échantillon | Forte régularisation (prior 30 matchs), bornes, tests synthétiques |
| Rétro-test biaisé par la sélection des matchs évaluables | Exclusions comptées, période affichée, avertissement explicite |
| Rétro-test lent | Plafond de 100 rencontres, chargement groupé, probabilités ponctuelles uniquement |
| Calibration interprétée comme garantie | Libellé « rétro-test », intervalles de Wilson, avertissement permanent |
| Fuite de données futures | Reconstruction stricte de l'historique avant coup d'envoi + test dédié |
| Régression du modèle v1 | Champs optionnels, tests v1 conservés, version `v2` explicite |
| Modification des combinaisons enregistrées | Aucune migration ni réécriture : les instantanés de la Phase 5 restent figés |
| Fuseaux horaires | Normalisation UTC comme dans les phases précédentes |

## Tests prévus

### Moteur
- xG : une équipe avec beaucoup de xG mais peu de buts obtient une attaque plus
  forte qu'avec les buts seuls.
- Proxy : tirs cadrés utilisés en l'absence de xG ; plafond respecté.
- Absence de statistiques : résultat identique au modèle « buts uniquement ».
- Couverture xG : pondérée correctement, avertissement sous le seuil.
- `rho` : données riches en scores faibles → `rho` plus négatif ; petit
  échantillon → proche du prior ; bornes et déterminisme.
- Calibration : prévisions parfaites → Brier et log loss nuls ; prévisions
  constantes → Brier de référence ; log loss borné ; ECE ; intervalles de
  Wilson ; effectifs par tranche ; déterminisme.
- Sommes des probabilités 1X2, ordre des fourchettes, reproductibilité.

### API
- Authentification requise pour la calibration.
- Métriques cohérentes avec les rencontres évaluées.
- Exclusions comptées lorsque l'historique est insuffisant.
- Aucune rencontre postérieure au coup d'envoi n'est utilisée (test de fuite).
- `limit` borné et appliqué ; base vide → réponse explicite sans erreur 500.
- La prédiction expose `v2`, les sources et le `rho` ; les champs v1 restent
  présents.
- Le xG saisi est réellement utilisé ; sans statistiques, repli sur les buts.

### Interface
- Panneau de prédiction v2 avec sources et avertissements.
- Page Calibration : chargement, sélecteur, indicateurs, tableau de fiabilité,
  état vide, avertissements.
- Navigation et affichage responsive.
- Aucune formulation certaine, aucune erreur console.

## Critères d'acceptation

1. Le moteur utilise le xG ou le proxy tirs cadrés lorsqu'ils existent, et
   retombe sur les buts sinon, sans inventer de valeur.
2. La couverture xG est affichée et avertit sous 50 %.
3. `rho` est estimé, régularisé, borné et visible dans la réponse.
4. Le rétro-test n'utilise que l'historique antérieur à chaque coup d'envoi et
   exclut les rencontres non évaluables en les comptant.
5. La page Calibration affiche Brier, log loss, précision, compétence Brier,
   ECE, tableau de fiabilité et taille d'échantillon.
6. Une base vide ou un historique insuffisant produit un message clair, pas
   une erreur ni une métrique inventée.
7. Les combinaisons enregistrées en Phase 5 restent inchangées et lisibles.
8. Le moteur reste pur et déterministe ; aucune nouvelle dépendance.
9. `ruff`, `mypy`, `pytest`, `eslint`, `tsc` et `next build` passent.

## Livrables

- `apps/api/engine/ratings.py` : xG, proxy, couverture, `rho` estimé.
- `apps/api/engine/calibration/` : métriques pures et tableau de fiabilité.
- `apps/api/engine/prediction.py` : version v2 et point/intervalle séparés.
- `apps/api/app/services/calibration.py` : rétro-test et chargement groupé.
- `apps/api/app/schemas/calibration.py`, `prediction.py` : schémas additifs.
- `apps/api/app/api/v1/predictions.py` : route de calibration.
- `apps/web/src/app/(app)/calibration/page.tsx` : page de mesure.
- `apps/web/src/components/match-prediction.tsx` : sources et version v2.
- Tests moteur, API et interface ; documentation `README.md` et
  `docs/exploitation/api.md`.

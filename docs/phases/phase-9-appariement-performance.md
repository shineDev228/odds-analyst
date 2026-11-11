# Phase 9 — Appariement des noms et vitesse de génération

> **Statut : validée le 11 novembre 2026.**
>
> Cette phase corrige deux défauts constatés lors de la vérification de bout en
> bout : des rencontres refusées à cause d'un appariement de noms trop strict, et
> une génération de combinaisons lente. Aucun calcul statistique ne change de
> résultat : les fourchettes restent identiques à la graine près.

## Objectifs

1. Apparier les événements de cotes dont le libellé d'équipe est abrégé
   (`Troyes` / `ESTAC Troyes`, `Lyon` / `Olympique Lyonnais`).
2. Ne jamais rendre cet appariement plus permissif à l'import des équipes.
3. Ramener la génération de combinaisons sous 2 secondes avec une dizaine de
   rencontres cotées.
4. Garantir que la version rapide produit exactement les mêmes chiffres.

## Décisions techniques

| Décision | Justification |
|---|---|
| Deux niveaux d'appariement | L'import d'équipes crée des données durables : il reste strict. L'appariement d'un événement de cotes est réversible et déjà encadré par le coup d'envoi. |
| `same_team` inchangé dans son principe | Égalité stricte après normalisation. Seuls les sigles de club (`RC`, `OGC`, `LOSC`, `ESTAC`…) sont désormais ignorés, car ils font partie du nom officiel et non de l'identité. |
| `same_team_relaxed` réservé aux cotes | Compare le « cœur » du nom après retrait des mots génériques (`Stade`, `Olympique`, `Entente`, `de`…) et des numéros. |
| Un seul qualificatif supplémentaire toléré | `Bordeaux` / `Girondins de Bordeaux` passe ; `Paris` / `Paris Saint-Germain` ne passe pas. Deux mots d'écart signalent une identité différente. |
| Toujours aucune fusion automatique | Un événement n'est associé que si **une seule** rencontre correspond, à ±30 minutes du coup d'envoi. Sinon l'utilisateur associe lui-même, et il peut corriger. |
| Simulation Monte-Carlo vectorisée | Les 1 000 matrices de scores sont construites en une passe au lieu de 1 000 appels unitaires. Même ordre de tirages aléatoires, même graine. |
| Historique partagé entre pronostics | `build_predictions` charge une fois les rencontres terminées utiles (`HistorySnapshot`), au lieu de quatre requêtes par rencontre. |
| Pas de cache mémoire | Un cache devrait être invalidé à chaque saisie de score, d'équipe ou de préférence. Le chargement groupé obtient le même gain sans risque de résultat périmé. |

## Appariement des noms

`apps/api/app/connectors/matching.py`

- `normalize_name` : minuscules, accents retirés, ponctuation neutralisée,
  sigles de club retirés en début et en fin de nom.
- `same_team` : égalité stricte d'une clé normalisée. Utilisée par
  `import_common.py` pour l'import CSV des équipes.
- `same_team_relaxed` : égalité stricte, ou même cœur de nom. Utilisée
  uniquement par `_resolve_event_match` dans `services/connectors.py`.

Exemples acceptés : `Troyes`, `Nice`, `Auxerre`, `Strasbourg`, `Lille`, `Lyon`,
`Rennes`, `Brest`, `Marseille`, `Lens`, `Bordeaux`.
Exemples refusés : `Lens` / `Lille`, `Le Havre` / `Le Mans`,
`Paris` / `Paris Saint-Germain`, `Stade Rennais` / `Stade Brestois 29`.

Effet secondaire assumé : deux clubs dont le nom ne diffère que par un
qualificatif (`Paris` / `Paris FC`) resteraient ambigus. La règle d'unicité et la
fenêtre de coup d'envoi empêchent l'association automatique, et l'écran
d'association reste la correction manuelle.

## Vitesse de génération

`apps/api/engine/models/poisson.py`

- Nouvelle `score_matrices` : mêmes bornes (`MIN_LAMBDA`/`MAX_LAMBDA`), même
  correction Dixon-Coles, même renormalisation, calcul par lots.
- `score_matrix` reste la référence unitaire, utilisée par le reste du moteur.

`apps/api/engine/uncertainty.py`

- Les six tirages log-normaux par simulation sont conservés dans le même ordre,
  puis les matrices sont construites en une seule fois.
- Les probabilités 1-X-2, « les deux équipes marquent » et les totaux sont
  extraites des matrices par masques NumPy.

`apps/api/app/services/predictions.py`

- `HistorySnapshot` : jusqu'à 1 200 rencontres terminées triées du plus récent au
  plus ancien, filtrées en mémoire par équipe et par date de coup d'envoi.
  L'échantillon de ligue passé au modèle reste borné à 400, comme avant.
- `build_predictions` : un chargement par sport et par date limite, puis un
  pronostic par rencontre. `build_prediction` conserve son comportement et
  s'appuie sur la même fonction de sérialisation (`_prediction_read`).

`apps/api/app/services/combinations.py`

- Les rencontres sans cote récente sont écartées **avant** tout calcul.
- Un seul appel à `build_predictions` remplace l'appel par rencontre.

### Mesure

Sur la copie de vérification (9 rencontres cotées, 207 rencontres programmées) :

| Étape | Avant | Après |
|---|---|---|
| Génération complète | 3,31 s | 0,91 s |
| Pronostic isolé | ~340–500 ms | ~130–330 ms |
| Matrices de scores par pronostic | 1 072 appels unitaires | 1 appel groupé |

La mesure dépend de la machine et du cache PostgreSQL ; l'ordre de grandeur
reste de 2 à 3 fois plus rapide, sous la barre des 2 secondes visée.

## Tests

| Fichier | Couverture |
|---|---|
| `apps/api/tests/test_connectors_mapping.py` | Abréviations françaises acceptées, clubs distincts refusés, import strict inchangé, double chance « RC Lens » |
| `apps/api/tests/test_engine_prediction.py` | `score_matrices` identique à `score_matrix` élément par élément, reproductibilité de `simulate_markets` |
| `apps/api/tests/test_predictions.py` | `build_predictions` identique à `build_prediction` (hors horodatage) |
| `apps/api/tests/test_combinations.py` | Génération via l'API inchangée |

Résultat : **241 tests** au total, `ruff` et `mypy` sans erreur ; `eslint` et
`tsc` sans erreur (aucune modification de l'interface).

## Risques et parades

| Risque | Parade |
|---|---|
| Un nom abrégé est associé au mauvais club | Fenêtre de ±30 minutes, deux équipes doivent correspondre, une seule rencontre candidate exigée, correction manuelle toujours possible |
| L'appariement permissif contamine les imports | `same_team_relaxed` n'est appelée que par l'appariement d'événements de cotes |
| La version vectorisée change les fourchettes | Même suite aléatoire et même graine ; test d'égalité élément par élément et test d'équivalence des pronostics |
| Le chargement partagé oublie un match ancien | Fenêtre de 1 200 rencontres terminées par sport (plusieurs saisons) ; l'échantillon de ligue reste borné à 400, comme avant |
| La génération reste lente sur une grosse base | Les rencontres sans cote sont écartées avant calcul ; la limite de 50 rencontres examinées reste en place |

## Ce que cette phase ne fait pas

- Aucune fusion automatique de deux équipes.
- Aucun scraping direct de bookmaker, aucun placement de pari.
- Aucune prédiction présentée comme certaine : les fourchettes d'incertitude
  restent affichées.
- Aucun changement de modèle statistique, de marché ou de règle de règlement.
- Aucun cache mémoire à invalider.

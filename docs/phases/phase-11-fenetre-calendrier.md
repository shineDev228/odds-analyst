# Phase 11 — Fenêtre de calendrier des connecteurs

> **Statut : validée le 12 novembre 2026.**
>
> Cette phase limite l'import du calendrier aux rencontres programmées à court
> terme. Les résultats passés restent importés sans limite : le modèle
> statistique a besoin de tout l'historique.

## Objectif

Éviter d'importer toute la saison d'un coup. Les connecteurs de calendrier
(`football_data.org` et `BigBallsData`) renvoyaient l'intégralité de la saison,
créant des centaines de rencontres programmées jusqu'en mai 2027, sans intérêt
immédiat pour la génération de combinaisons.

## Décision

| Décision | Justification |
|---|---|
| Fenêtre de **10 jours** | Assez large pour couvrir la journée en cours ou la reprise après une trêve, assez courte pour ne pas encombrer la base. |
| Fenêtre glissante à partir du jour de l'aperçu | Le comportement est prévisible et ne dépend pas du calendrier de la compétition. |
| Les rencontres non « programmées » restent importées | Les résultats, annulations et autres statuts alimentent l'historique ou informent ; les filtrer casserait le modèle. |
| Filtre commun aux deux fournisseurs de calendrier | Le code de planification est partagé ; une seule règle s'applique partout. |
| Avertissement explicite dans l'aperçu | L'utilisateur voit combien de rencontres ont été écartées et pourquoi. |

Pourquoi 10 jours et non 7 : au moment de la correction, aucune rencontre
n'était programmée avant le 20 novembre (trêve internationale), soit huit jours
plus tard. Une fenêtre stricte de 7 jours aurait affiché un calendrier vide.

## Implémentation

`apps/api/app/services/connectors.py`

- Constante `FIXTURE_WINDOW_DAYS = 10`.
- `_within_fixture_window` conserve toutes les rencontres dont le statut n'est
  pas `programme`, et les rencontres `programme` dont le coup d'envoi est
  inférieur ou égal à `maintenant + 10 jours`.
- `preview_fixtures` applique ce filtre après normalisation des données du
  fournisseur, avant `plan_matches`.
- Le compteur « reçues » conserve le nombre total renvoyé par le fournisseur ;
  les rencontres écartées apparaissent dans un avertissement avec la date
  limite.

Aucun changement du côté de The Odds API ni du connecteur CSV : le premier
n'importe pas de calendrier, le second ne fournit que des résultats.

## Données existantes

Sur la base réelle, 465 rencontres programmées au-delà de la fenêtre ont été
supprimées, ainsi que leurs références externes. Ont été conservés :

- 209 rencontres terminées (historique du modèle) ;
- 11 rencontres programmées les 20 et 21 novembre ;
- 1 rencontre annulée, qui n'est pas un match programmé.

Aucune combinaison enregistrée n'était concernée. Les marchés et cotes liés aux
rencontres supprimées ont été retirés par les cascades existantes.

## Tests

| Fichier | Couverture |
|---|---|
| `apps/api/tests/test_connectors_import.py` | Une rencontre à 3 jours est importée, une à 20 jours est écartée, un résultat ancien reste importé ; l'avertissement et les compteurs sont vérifiés |
| `apps/api/tests/test_connectors_import.py` | Limite exacte : 10 jours conservé, 10 jours et 1 seconde écarté ; un statut non « programme » reste conservé quelle que soit la date |
| `apps/api/tests/test_connectors_api.py` | L'aperçu et l'application via l'API restent fonctionnels avec une date dynamique |

Les dates des tests ne sont plus figées : elles sont calculées à partir du jour
d'exécution, pour que la suite reste valable dans le temps.

## Risques et parades

| Risque | Parade |
|---|---|
| Une rencontre utile tombe juste après la fenêtre | Avertissement avec la date limite ; relancer l'aperçu plus tard. La fenêtre de 10 jours couvre la journée en cours. |
| L'historique est tronqué | Seules les rencontres `programme` sont filtrées ; les résultats passés ne le sont jamais. |
| L'aperçu semble incomplet | Le compteur « reçues » indique le total fournisseur et l'avertissement précise le nombre écarté. |
| Les tests deviennent obsolètes avec une date figée | Dates calculées à l'exécution ; test de limite explicite. |

## Ce que cette phase ne fait pas

- Aucune modification du moteur statistique.
- Aucune suppression de résultats passés.
- Aucun changement des quotas, des appels réseau ou des fournisseurs.
- Aucune fenêtre configurable dans l'interface : la valeur est fixe pour
  l'instant.

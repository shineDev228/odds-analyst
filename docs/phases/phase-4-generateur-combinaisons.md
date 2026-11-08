# Phase 4 — Générateur de combinaisons

> **Statut : validée.** Assemblage de sélections dont la cote totale tombe
> dans la fourchette visée, avec estimation de probabilité et avertissements.

## Objectif

Proposer des **combinaisons de sélections** issues des rencontres à venir et
des cotes saisies, dont la **cote totale** est comprise entre `cote_min` et
`cote_max` (50 et 100 par défaut). Chaque combinaison affiche sa cote totale,
sa probabilité estimée, sa fourchette d'incertitude et son espérance
mathématique.

Le générateur ne place aucun pari et ne présente aucune combinaison comme
certaine. Il aide à comparer des assemblages plausibles ; il ne recommande pas
de miser.

## Périmètre v1

- **Football uniquement**, comme le moteur statistique v1.
- Marchés couverts par le modèle : **1X2**, **double chance** et **totaux de
  buts** aux lignes 1,5 / 2,5 / 3,5.
- Seules les rencontres **programmées** et **à venir** sont utilisées.
- Une combinaison contient **exactement** le nombre de sélections demandé
  (valeur par défaut : préférence `nb_selections_defaut`).
- **Une seule sélection par rencontre** dans une combinaison, pour limiter les
  dépendances entre résultats.
- Seules les sélections ayant une **cote récente** et une **probabilité
  estimée** sont retenues. Une rencontre sans historique suffisant est ignorée
  et signalée dans les compteurs.

## Hors périmètre (phases suivantes)

- Historique des combinaisons et suivi de performance (Phase 5).
- Autres sports et marchés non couverts par le modèle v1 (Phase 6/7).
- Optimisation avancée, apprentissage automatique, bankroll.
- Placement automatique de paris : jamais.

## Décisions techniques

### 1. Moteur pur, service d'orchestration

Le calcul combinatoire est placé dans `apps/api/engine/combos/generator.py` :
il ne connaît ni la base de données ni FastAPI. Le service
`app/services/combinations.py` charge les rencontres, calcule les prédictions
et transforme les sélections en candidats.

### 2. Recherche bornée et déterministe

L'énumération exhaustive de toutes les combinaisons est impossible dès que le
nombre de rencontres augmente. Le générateur utilise une recherche
profondeur d'abord avec :

- une seule sélection par groupe (rencontre) ;
- des bornes sur le produit des cotes restantes pour éliminer les branches
  impossibles ;
- un nombre maximal de nœuds explorés ;
- un classement final par espérance estimée, puis par probabilité et par
  proximité du milieu de la fourchette.

Le résultat est **déterministe** : mêmes données et mêmes paramètres donnent
les mêmes combinaisons.

### 3. Probabilité et espérance

Pour une combinaison de rencontres distinctes, les résultats sont supposés
indépendants :

```
probabilité = produit des probabilités estimées
cote_totale = produit des cotes décimales
espérance = probabilité × cote_totale − 1
```

La fourchette basse/haute est le produit des bornes basses/hautes de chaque
sélection. Elle reste une estimation, pas une garantie.

### 4. Paramètres

- `nombre_selections` : 2 à 15, valeur par défaut issue des préférences.
- `cote_min` / `cote_max` : valeurs par défaut issues des préférences.
- `marches_autorises` : sous-ensemble de `1X2`, `DOUBLE_CHANCE`,
  `PLUS_MOINS`, par défaut les préférences.
- `limite` : nombre maximal de combinaisons retournées (10 par défaut).

L'interface permet de modifier ces valeurs sans changer les préférences
enregistrées.

### 5. API sans persistance

`POST /combinations/generate` calcule à la demande. Aucune combinaison n'est
stockée en Phase 4 : l'historique et la mesure de performance viendront en
Phase 5.

## Risques et parades

| Risque | Parade |
|---|---|
| Explosion combinatoire | Recherche bornée, élagage par cotes, limite de nœuds |
| Combinaisons corrélées | Une seule sélection par rencontre |
| Probabilités présentées comme certaines | Libellé « estimée », fourchette obligatoire, avertissement permanent |
| Données de cotes incomplètes | Seules les sélections avec cote et probabilité sont retenues ; compteurs explicites |
| Historique insuffisant | Rencontres ignorées et signalées, aucune probabilité inventée |
| Espérance négative cachée | Affichage explicite de l'espérance estimée, sans promesse de gain |
| Résultats différents selon l'ordre des données | Tri déterministe et tests de reproductibilité |

## Tests prévus

### Moteur
- Respect du nombre exact de sélections et d'une seule sélection par rencontre.
- Cote totale dans la fourchette demandée.
- Produit des probabilités et fourchettes cohérent.
- Classement par espérance décroissante.
- Aucun résultat si les groupes sont insuffisants ou la fourchette impossible.
- Reproductibilité avec les mêmes entrées.
- Rejet des paramètres invalides.

### API
- Authentification requise.
- Réponse vide explicite sans données exploitables.
- Combinaisons cohérentes avec les cotes saisies et les prédictions.
- Application des préférences et des paramètres de la requête.
- Rencontres sans historique ignorées avec compteur.
- Validation des fourchettes et des marchés autorisés.

### Interface
- Nouvelle page « Combinaisons » dans la navigation.
- Formulaire prérempli avec les préférences.
- Affichage de la cote totale, de la probabilité, de la fourchette et de
  l'espérance.
- Détail de chaque sélection (rencontre, marché, choix, cote).
- États vides et erreurs explicites, sans formulation certaine.

## Critères d'acceptation

1. Une combinaison générée contient exactement le nombre de sélections demandé.
2. Aucune combinaison ne contient deux sélections de la même rencontre.
3. La cote totale de chaque combinaison est dans la fourchette demandée.
4. La probabilité et la fourchette sont affichées pour chaque combinaison.
5. Les rencontres sans historique ou sans cote sont ignorées et comptées.
6. Le moteur reste pur et déterministe.
7. `ruff`, `mypy`, `pytest`, `eslint`, `tsc` et `next build` passent.

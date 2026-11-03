# ADR 0001 — Stack technique de ODDS ANALYST

- **Statut** : Accepté
- **Date** : 2026-11-03
- **Décideur** : Propriétaire du projet

## Contexte

ODDS ANALYST est une application web personnelle d'analyse statistique sportive,
destinée à un utilisateur unique. Elle doit :

- estimer des probabilités à partir de statistiques historiques ;
- comparer ces estimations aux cotes d'un bookmaker ;
- générer des combinaisons de cotes comprises entre 50 et 100 ;
- mesurer la calibration des estimations dans le temps ;
- rester maintenable par une personne non développeuse ;
- n'utiliser que des technologies open source et gratuites.

## Décision

Architecture en **monolithe modulaire** composé de deux processus :

| Couche | Technologie |
|---|---|
| Interface | Next.js 15 (App Router), React, TypeScript, Tailwind CSS, shadcn/ui |
| API | Python 3.12, FastAPI, Pydantic v2 |
| Moteur statistique | Paquet Python pur : NumPy, SciPy |
| Persistance | PostgreSQL 16, SQLAlchemy 2, Alembic |
| Tests | pytest, Hypothesis, Playwright |

Le moteur statistique (`apps/api/engine/`) est un paquet **sans aucune
dépendance d'entrée/sortie** : ni base de données, ni HTTP, ni fichier.
Il expose des fonctions pures, testables isolément.

## Justification

1. **Python pour le moteur** : l'estimation par maximum de vraisemblance
   (Dixon-Coles), le bootstrap et les tests de calibration sont nettement
   plus fiables et rapides à écrire avec NumPy/SciPy qu'en TypeScript.
   Le moteur est le cœur du produit : il mérite le meilleur outil.
2. **Next.js pour l'interface** : rendu serveur, routage intégré, écosystème
   mature, et composants shadcn/ui dont nous possédons le code (aucun verrou).
3. **PostgreSQL** : précision décimale (`numeric`) indispensable pour comparer
   des cotes, JSONB pour les paramètres variables, fonctions de fenêtrage
   pour les statistiques.
4. **Monolithe plutôt que microservices** : un utilisateur unique ne justifie
   pas une complexité opérationnelle supplémentaire.

## Alternatives écartées

| Alternative | Motif du rejet |
|---|---|
| Tout TypeScript | Calculs statistiques avancés plus longs à développer et moins fiables |
| Django + templates | Interface moins moderne, exigence UI du cahier des charges |
| Microservices | Complexité injustifiée pour un utilisateur unique |
| SQLite | Migration douloureuse sur les types décimaux et les statistiques avancées |
| MongoDB | Données fortement relationnelles, jointures statistiques nécessaires |

## Conséquences

- Deux environnements d'exécution à maintenir (Node et Python) → scripts de
  démarrage unifiés dans `infra/scripts/`.
- Le contrat d'API est la seule interface entre les deux processus ; le client
  TypeScript est généré depuis OpenAPI pour éviter toute désynchronisation.
- Toute logique métier ajoutée dans l'interface serait une violation de
  l'architecture et doit être refusée en revue.

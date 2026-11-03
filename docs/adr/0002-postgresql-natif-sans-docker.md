# ADR 0002 — PostgreSQL natif sous Windows, sans Docker

- **Statut** : Accepté
- **Date** : 2026-11-03
- **Décideur** : Propriétaire du projet

## Contexte

L'architecture initiale prévoyait un déploiement via Docker Compose
(conteneurs `web`, `api`, `db`), pour garantir la reproductibilité de
l'environnement et simplifier les sauvegardes.

La machine de développement a été analysée :

| Élément | Valeur constatée |
|---|---|
| Système | Windows 10 Professionnel |
| Version | 1909 (build 18363) |
| Fin de support Microsoft | Juin 2021 |
| Espace disque libre | ~132 Go |

**Docker Desktop exige Windows 10 version 21H2 (build 19044) minimum.**
Il ne peut donc pas être installé sur cette machine en l'état.

## Décision

1. **PostgreSQL 16 est installé nativement sous Windows**, en tant que service.
2. Un **rôle applicatif dédié** (`odds_analyst_app`) est créé, avec des droits
   limités à la base `odds_analyst` — jamais le superutilisateur `postgres`.
3. Un fichier `docker-compose.yml` est conservé dans le dépôt, prêt à l'emploi,
   mais **n'est pas requis** pour le développement.
4. Les sauvegardes utilisent `pg_dump` via un script PowerShell planifié.

## Justification

- Aucune dépendance à une mise à jour du système d'exploitation.
- Une couche de virtualisation en moins : moins de points de panne pour un
  utilisateur non technique.
- Migration ultérieure vers Docker triviale : `pg_dump` puis restauration.

## Risques et parades

| Risque | Parade |
|---|---|
| Service PostgreSQL arrêté après redémarrage | Service configuré en démarrage automatique ; script de diagnostic |
| Mot de passe du superutilisateur perdu | Stocké dans le gestionnaire de mots de passe Windows ; procédure de réinitialisation documentée dans `docs/exploitation/` |
| Sauvegardes non exécutées | Tâche planifiée + contrôle de la date de la dernière sauvegarde dans `/system/info` |

## Action recommandée, indépendante du projet

Windows 10 version 1909 n'est plus maintenue depuis juin 2021.
Une mise à jour vers la version 22H2 est recommandée pour la sécurité de la
machine. Elle n'est pas bloquante pour ODDS ANALYST.

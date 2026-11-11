# Phase 8 — Durcissement et documentation

> **Statut : validée le 11 novembre 2026.**
>
> Cette phase ne modifie aucun calcul statistique. Elle rend l'application plus
> difficile à attaquer, plus simple à sauvegarder et à diagnostiquer. Elle ne
> change ni le caractère incertain des estimations, ni l'interdiction de placer
> un pari automatiquement.

## Objectifs

1. Poser des en-têtes de sécurité sur l'API et l'interface.
2. Fermer les sessions inactives et purger les sessions périmées.
3. Couvrir les protections par des tests reproductibles.
4. Rendre la sauvegarde et la restauration sûres, avec une base de test.
5. Documenter l'exploitation courante : journaux, quotas, dépannage.
6. Accélérer les lectures fréquentes par deux index composites.

## Décisions techniques

| Décision | Justification |
|---|---|
| CSP par nonce uniquement en production | React et le rafraîchissement à chaud ont besoin de scripts en ligne en développement. Le profil de production reste strict. |
| CSP posée par `apps/web/src/middleware.ts` | La politique dépend d'un nonce aléatoire par requête ; `next.config.ts` ne peut pas le générer. |
| HSTS conditionné à `COOKIE_SECURE` | HSTS n'a de sens qu'en HTTPS. En développement HTTP, l'envoyer bloquerait le navigateur. |
| Expiration d'inactivité de 12 h | Une session oubliée ne reste pas valide 24 h. La valeur est réglable. |
| `last_seen_at` réécrit au plus toutes les 60 s | Évite une écriture en base à chaque requête. |
| Purge au démarrage et à la validation | Les sessions expirées ou inactives sont supprimées au lieu de rester indéfiniment. |
| Restauration par défaut dans `odds_analyst_restore_test` | Une restauration détruit la base cible. La base de travail n'est jamais visée par défaut. |
| Confirmation manuelle pour la base réelle | Même avec `-ForceProduction`, le nom de la base doit être saisi. |
| Journalisation JSON avec la bibliothèque standard | Aucun service externe, aucune dépendance payante. |
| Deux index composites | Lectures fréquentes : calendrier d'une saison et journal des synchronisations. |

## En-têtes de sécurité

### API (`apps/api/app/core/middleware.py`)

| En-tête | Valeur |
|---|---|
| `Content-Security-Policy` | `default-src 'none'` sur `/api/*` ; profil adapté à Swagger sur `/docs` |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `no-referrer` |
| `Cross-Origin-Opener-Policy` | `same-origin` |
| `Cross-Origin-Resource-Policy` | `same-origin` |
| `Permissions-Policy` | caméra, micro, géolocalisation, paiement et USB désactivés |
| `Cache-Control` | `no-store` sur les routes `/api/*` |
| `Strict-Transport-Security` | seulement si `COOKIE_SECURE=true` |
| `X-Request-ID` | identifiant fourni ou généré, repris dans les journaux |

### Interface (`apps/web/next.config.ts` et `apps/web/src/middleware.ts`)

- Mêmes en-têtes de base, plus `X-DNS-Prefetch-Control: off`.
- CSP de développement : `unsafe-inline` et `unsafe-eval` pour React.
- CSP de production : nonce par requête, `strict-dynamic`, `upgrade-insecure-requests`.
- Les routes `/api` sont exclues du middleware web : l'API pose elle-même ses
  en-têtes.

## Sessions

- Expiration absolue : `SESSION_MAX_AGE_SECONDS` (24 h).
- Expiration d'inactivité : `SESSION_IDLE_SECONDS` (12 h).
- Rafraîchissement : `SESSION_TOUCH_SECONDS` (60 s).
- États distingués : session inconnue, expirée, inactive. Les messages français
  sont distincts pour aider au diagnostic sans révéler d'information sensible.
- Purge : au démarrage de l'API et à chaque résolution de session périmée.

## Journalisation

- Une ligne JSON par événement : horodatage UTC, niveau, journal, message.
- `request_id` ajouté quand la requête en possède un.
- Les requêtes de plus de 2 secondes sont signalées.
- Aucun corps de requête, cookie, jeton ou clé de fournisseur n'est journalisé.

Exemple :

```json
{"time":"2026-11-10T21:00:00.000+00:00","level":"INFO","logger":"odds_analyst.http","message":"requete method=GET path=/api/v1/matches status=200 duration_ms=42","request_id":"3f2a…"}
```

## Robustesse

- Pagination bornée : `page_size` maximal de 100 à 200 selon la route.
- Journal des synchronisations borné à 100 entrées par requête.
- Délai maximal de 60 s dans le client web, avec message explicite.
- Index ajoutés :
  - `matches (season_id, kickoff_at)` : liste d'une saison triée par date ;
  - `sync_runs (created_at)` : journal lu du plus récent au plus ancien.
- Migration `a1b2c3d4e5f6` strictement additive.

## Tests

| Fichier | Couverture |
|---|---|
| `apps/api/tests/test_security.py` | En-têtes, HSTS conditionnel, CSP Swagger, session expirée, session inactive, throttle de `last_seen_at`, purge, matrice CSRF, jeton incohérent |
| `apps/api/tests/test_auth.py` | Amorçage, connexion, déconnexion, limitation des tentatives, CSRF |
| `apps/api/tests/test_health.py` | Santé de l'API et de la base |

Résultat : **235 tests** au total, `ruff` et `mypy` sans erreur.

## Risques et parades

| Risque | Parade |
|---|---|
| La CSP casse l'interface en production | Profil de développement distinct et vérification manuelle après `next build` |
| Une session inactive déconnecte trop tôt | 12 h par défaut, valeur réglable dans `.env` |
| La restauration écrase la base de travail | Base de test par défaut et confirmation saisie pour la base réelle |
| Les journaux contiennent un secret | Aucun en-tête ni corps journalisé ; les paramètres sensibles des URL sont masqués |
| Les index ralentissent les écritures | Deux index seulement, sur des colonnes de lecture fréquente |

## Ce que cette phase ne fait pas

- Aucune exposition de l'application sur Internet.
- Aucun scraping direct de bookmaker.
- Aucune prédiction présentée comme certaine.
- Aucun placement automatique de pari.

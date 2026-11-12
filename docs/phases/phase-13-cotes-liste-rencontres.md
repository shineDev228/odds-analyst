# Phase 13 — Cotes 1X2 dans la liste des rencontres

> **Statut : validée le 12 novembre 2026.**
>
> Chaque ligne de la page « Rencontres » affiche désormais les trois dernières
> cotes 1X2. Il n'est plus nécessaire d'ouvrir chaque fiche pour savoir si une
> rencontre est cotée.

## Objectif

Rendre lisible d'un coup d'œil l'état des cotes du calendrier. Avant cette
phase, les cotes n'apparaissaient que dans le panneau « Marchés et cotes » de la
fiche d'une rencontre, tout en bas de la page. Pour parcourir plusieurs
rencontres, il fallait ouvrir chaque fiche.

## Décisions

| Décision | Justification |
|---|---|
| Aperçu limité au marché **1X2** | Trois valeurs tiennent sur une ligne et suffisent à repérer une rencontre cotée. Les autres marchés restent sur la fiche. |
| Affichage de la **dernière cote** de chaque issue | C'est la cote que le générateur utilise ; afficher un ancien relevé serait trompeur. |
| Mention « Aucune cote 1X2 » | Distingue clairement une rencontre non cotée d'une rencontre dont les cotes seraient à zéro. |
| Calcul groupé côté API | Une seule requête pour toutes les rencontres de la page, afin de ne pas multiplier les appels. |
| Champ **facultatif** `odds_1x2` | Les autres écrans qui réutilisent le même schéma (tableau de bord) restent compatibles sans calcul supplémentaire. |

## Implémentation

`apps/api/app/schemas/match.py`

- `Odds1x2Read` : `home`, `draw`, `away`, chacun facultatif.
- `MatchListItem.odds_1x2` : résumé facultatif.

`apps/api/app/api/v1/matches.py`

- `_odds_1x2(db, match_ids)` : sélectionne les cotes des marchés `resultat`,
  période `match`, sujet `match`, codes `1`, `X`, `2`, et ne garde que le
  dernier relevé par sélection (sous-requête `max(captured_at)`).
- `list_matches` calcule ce résumé en une requête pour toute la page, puis le
  transmet à `_to_list_item`.
- Les rencontres sans marché 1X2 renvoient `odds_1x2: null`.

`apps/web/src/lib/types.ts`

- `Cotes1x2` et `Rencontre.odds_1x2`.

`apps/web/src/app/(app)/rencontres/page.tsx`

- Composant `ApercuCotes1x2` : trois petites cases « 1 », « X », « 2 » avec la
  cote formatée en français (virgule, deux décimales).
- Infobulle sur chaque case : nom de l'équipe ou « Match nul ».
- « Aucune cote 1X2 » lorsque les trois valeurs sont absentes.
- Le sous-titre de la page annonce l'aperçu.

## Tests

| Fichier | Couverture |
|---|---|
| `apps/api/tests/test_matches.py` | La liste expose les cotes 1X2 saisies à la création du marché |
| `apps/api/tests/test_matches.py` | Après un nouveau relevé, la cote la plus récente est renvoyée |
| `apps/api/tests/test_matches.py` | Une rencontre sans marché 1X2 renvoie `odds_1x2: null` |

Vérification sur la base réelle : la rencontre du 21 novembre cotée à
1,89 / 4,11 / 4,11 est correctement résumée ; les dix autres rencontres
programmées renvoient `null`.

## Risques et parades

| Risque | Parade |
|---|---|
| La liste devient chargée | Trois valeurs compactes seulement, alignées à droite ; le reste de la ligne est inchangé. |
| Une cote ancienne est prise pour la cote actuelle | Seul le dernier relevé est affiché ; la fiche montre l'historique complet. |
| Plusieurs marchés « resultat » sur une rencontre | La cote la plus récente par code est retenue. |
| Performance de la liste | Une requête unique pour la page, avec agrégation du dernier relevé par sélection. |
| Affichage sur petit écran | La zone de droite passe à la ligne grâce au `flex-wrap`. |

## Ce que cette phase ne fait pas

- Aucune modification du calcul des probabilités ni du générateur.
- Aucun aperçu des autres marchés dans la liste : ils restent sur la fiche.
- Aucune modification du tableau de bord : son champ `odds_1x2` reste vide.
- Aucune saisie de cote depuis la liste : la fiche reste le lieu de saisie.

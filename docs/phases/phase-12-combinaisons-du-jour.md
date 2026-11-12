# Phase 12 — Combinaisons limitées aux rencontres du jour

> **Statut : validée le 12 novembre 2026.**
>
> Le générateur ne travaille plus sur toutes les rencontres à venir : il se
> limite au jour calendaire courant. S'il ne reste aucune rencontre exploitable
> aujourd'hui, il bascule sur le prochain jour de match avec des cotes récentes.

## Objectif

Éviter que le générateur assemble des combinaisons avec des rencontres prévues
plusieurs semaines ou plusieurs mois à l'avance. Une combinaison doit porter sur
les matchs du jour, c'est-à-dire ceux dont le coup d'envoi est encore à venir
aujourd'hui.

## Décisions

| Décision | Justification |
|---|---|
| Jour **calendaire** dans le fuseau `Europe/Paris` | Correspond à la journée vécue par l'utilisateur ; le réglage `app_timezone` existait déjà. |
| Les matchs **déjà commencés** sont exclus | Une rencontre en cours ne peut plus être jouée. |
| Repli sur le **prochain jour de match avec des cotes** | Évite un écran vide quand la journée est terminée ou sans rencontre, tout en ne proposant que des rencontres réellement exploitables. |
| Si aucun jour n'a de cotes, le premier jour de match est retenu | Le message explique alors clairement que les cotes manquent, au lieu d'une réponse vide sans contexte. |
| Un maximum de **50 rencontres** reste appliqué | Protection existante du moteur ; le jour choisi est déterminé parmi ces rencontres. |
| Le jour retenu et le repli sont exposés par l'API | `jour_cible` et `repli_jour` permettent à l'interface d'afficher une information explicite. |

Pourquoi un repli sur les cotes : au moment de la correction, le prochain jour
de match était le 20 novembre (2 rencontres), mais les seules cotes saisies
portaient sur une rencontre du 21. Un repli strict sur la date aurait affiché
« aucune rencontre exploitable » alors qu'un jour exploitable existait le
lendemain.

## Implémentation

`apps/api/app/services/combinations.py`

- `_now()` : horloge interne, remplaçable dans les tests.
- `_local_day()` : convertit un instant UTC en jour calendaire dans le fuseau de
  l'application.
- `_upcoming_matches()` : charge les rencontres programmées à venir, triées,
  limitées à 50.
- `_has_recent_odds()` : vérifie qu'une rencontre possède au moins une cote
  récente sur un marché autorisé.
- `_select_day()` : regroupe les rencontres par jour local, retient le jour
  courant s'il est exploitable, sinon le premier jour suivant avec cotes, sinon
  le premier jour avec rencontres. Retourne le jour, l'indicateur de repli, les
  rencontres du jour et la présence de cotes.
- `build_combinations()` utilise ce jour unique pour tout le calcul.

`apps/api/app/schemas/combination.py`

- `jour_cible: date | None` : jour effectivement analysé.
- `repli_jour: bool` : vrai lorsque le jour retenu n'est pas aujourd'hui.

`apps/web/src/app/(app)/combinaisons/page.tsx`

- La règle est annoncée dans la description du panneau de critères.
- Le bandeau de résultat affiche « Rencontres du … » ou « Aucune rencontre
  aujourd'hui : prochain jour de match, le … ».
- L'état vide parle du jour analysé.

## Tests

| Fichier | Couverture |
|---|---|
| `apps/api/tests/test_combinations.py` | Une rencontre du jour est examinée, une rencontre du lendemain est écartée |
| `apps/api/tests/test_combinations.py` | Repli sur le lendemain quand aujourd'hui est vide, avec message explicite |
| `apps/api/tests/test_combinations.py` | Le repli saute un jour sans cotes pour trouver le premier jour coté |
| `apps/api/tests/test_combinations.py` | Sans aucune cote, le message indique le jour retenu et l'absence de cotes |

L'horloge du service est figée dans les tests (`_now` remplacé par une fixture
autouse) afin que « aujourd'hui » reste stable quelle que soit l'heure
d'exécution. Les dates restent calculées à l'exécution : la suite ne périme pas.

## Risques et parades

| Risque | Parade |
|---|---|
| Un match du jour commence pendant la recherche | La borne basse est l'instant présent ; un match déjà commencé est exclu. |
| Le jour courant n'a aucune cote | Repli explicite sur le prochain jour coté, avec message. |
| Le prochain jour coté est très éloigné | Le générateur reste borné aux 50 prochaines rencontres et la fenêtre d'import des connecteurs est de 10 jours. |
| L'utilisateur croit que les combinaisons portent sur plusieurs jours | Le jour retenu est affiché dans le bandeau et documenté au guide (section 10). |
| Fuseau horaire différent du navigateur | Le serveur applique `app_timezone` (`Europe/Paris`), référence unique de la journée. |

## Ce que cette phase ne fait pas

- Aucun changement du moteur statistique ni du calcul des probabilités.
- Aucune modification des marchés autorisés.
- Aucune sélection manuelle d'un autre jour dans l'interface.
- Aucune suppression des rencontres des jours suivants : elles restent
  consultables et seront utilisées le jour venu.

## Vérification sur la base réelle

Le 12 novembre 2026 :

- aucun match aujourd'hui ; prochain jour de match : 20 novembre (2 rencontres) ;
- seules cotes présentes : une rencontre du 21 novembre (5 sélections) ;
- jour retenu par le générateur : **21 novembre**, avec repli ;
- 9 rencontres examinées ce jour-là, 1 exploitable, 5 sélections disponibles ;
- aucune combinaison possible avec 2 sélections tant que d'autres cotes ne sont
  pas saisies, ce que le message indique explicitement.

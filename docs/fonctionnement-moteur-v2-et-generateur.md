# Comment fonctionnent le moteur V2 et le générateur de combinaisons

> **Document explicatif.** Il décrit le fonctionnement réel du code livré en
> version 1.1.0. Il ne remplace pas le guide d'utilisation : il explique ce qui
> se passe « sous le capot », avec les formules et les paramètres exacts.
>
> **À retenir d'emblée :** le moteur V2 n'est pas de l'intelligence
> artificielle et n'apprend pas tout seul. C'est un modèle statistique
> explicable, fondé sur les buts, les tirs cadrés et le xG que vous saisissez.
> Il produit des **probabilités estimées**, jamais des certitudes.

---

## Sommaire

1. [Vue d'ensemble](#1-vue-densemble)
2. [Vocabulaire utile](#2-vocabulaire-utile)
3. [Le moteur V2, étape par étape](#3-le-moteur-v2-étape-par-étape)
4. [Un exemple chiffré complet](#4-un-exemple-chiffré-complet)
5. [Les fourchettes d'incertitude](#5-les-fourchettes-dincertitude)
6. [Le générateur de combinaisons](#6-le-générateur-de-combinaisons)
7. [Pourquoi certaines combinaisons n'apparaissent pas](#7-pourquoi-certaines-combinaisons-napparaissent-pas)
8. [Garanties, limites et réglages](#8-garanties-limites-et-réglages)
9. [Où se trouve le code](#9-où-se-trouve-le-code)

---

## 1. Vue d'ensemble

Deux blocs distincts travaillent l'un après l'autre.

```
Votre historique (matchs terminés, scores, xG, tirs cadrés)
        │
        ▼
┌─────────────────────────────────────────────┐
│  MOTEUR V2  (apps/api/engine/)              │
│  « Quelle est la probabilité de chaque      │
│    résultat pour cette rencontre ? »        │
│                                             │
│  forces → buts attendus → matrice de scores │
│  → probabilités → fourchettes               │
└─────────────────────────────────────────────┘
        │  probabilités par sélection
        ▼
┌─────────────────────────────────────────────┐
│  GÉNÉRATEUR  (engine/combos/ + service)     │
│  « Quelles sélections assembler pour que    │
│    la cote totale tombe entre 50 et 100 ? » │
│                                             │
│  candidats → recherche → classement         │
└─────────────────────────────────────────────┘
        │
        ▼
Combinaisons affichées avec cote totale,
probabilité estimée, fourchette et espérance
```

Le moteur ne connaît **ni la base de données, ni l'interface, ni Internet**.
Il reçoit des listes de matchs et des paramètres, et rend des nombres. C'est ce
qui rend ses calculs reproductibles et testables séparément.

Le générateur, lui, est en deux parties :

- `apps/api/engine/combos/generator.py` : la recherche combinatoire pure ;
- `apps/api/app/services/combinations.py` : la partie « application », qui
  choisit le jour, charge l'historique, calcule les pronostics et prépare les
  candidats.

---

## 2. Vocabulaire utile

| Terme | Sens dans ODDS ANALYST |
|---|---|
| **xG** (buts attendus) | Nombre de buts qu'une équipe « aurait dû » marquer selon la qualité de ses occasions. Vous le saisissez dans les statistiques de la rencontre. |
| **Tirs cadrés** | Tirs qui auraient fini au fond sans le gardien ou le poteau. Sert de remplacement au xG quand il est absent. |
| **λ (lambda)** | Nombre moyen de buts attendus pour une équipe dans un match donné. |
| **Demi-vie** | Nombre de jours au bout duquel un match compte moitié moins qu'un match du jour. 240 jours par défaut. |
| **Matchs effectifs** | Nombre de matchs « équivalents » après pondération par la récence. 10 matchs très récents valent plus que 10 matchs étalés sur trois ans. |
| **Dixon-Coles / rho (ρ)** | Petite correction qui ajuste la fréquence des scores serrés (0-0, 1-0, 0-1, 1-1), que le modèle de Poisson simple décrit mal. |
| **Matrice de scores** | Tableau de toutes les probabilités « score exact » (0-0, 1-0, 2-1, etc.). Tous les marchés en sont déduits. |
| **Fourchette 80 %** | Intervalle entre les percentiles 10 et 90 de 1 000 simulations. Il reflète l'incertitude sur les forces estimées, pas une garantie. |
| **Cote décimale** | Format européen : 2,10 signifie que 1 unité mise rapporte 2,10 unités si la sélection gagne. |
| **Espérance (EV)** | `probabilité × cote − 1`. Positive, elle indique un avantage théorique ; négative, la marge du bookmaker joue contre vous. |

---

## 3. Le moteur V2, étape par étape

Le code d'orchestration est `engine/prediction.py`. La version exposée est
`football-poisson-v2`.

### Étape 1 — Charger uniquement le passé

Avant chaque rencontre, l'application charge les matchs **terminés**, avec un
score, dont le coup d'envoi est **strictement antérieur** à celui de la
rencontre analysée. Aucune information future ne peut entrer dans le calcul.

- jusqu'à **38 matchs** par équipe (préférence `nb_matchs_historique`) ;
- jusqu'à **400 matchs** pour la moyenne du championnat ;
- pour le générateur, un instantané plus large (1 200 matchs) est chargé une
  seule fois, puis découpé pour chaque rencontre.

Il faut au moins **3 matchs terminés par équipe**. En dessous, le moteur refuse
de produire une estimation : il vaut mieux aucun chiffre qu'un chiffre inventé.

### Étape 2 — Donner plus de poids aux matchs récents

Chaque match reçoit un poids décroissant :

```
poids = 0,5 ^ (jours_écoulés / demi_vie)
```

Avec la demi-vie de 240 jours :

| Ancienneté du match | Poids |
|---|---|
| Aujourd'hui | 1,00 |
| 4 mois | 0,50 |
| 8 mois | 0,25 |
| 2 ans | 0,12 |

Un match d'il y a deux ans pèse donc huit fois moins qu'un match récent. La
demi-vie est réglable entre 30 et 730 jours dans les préférences.

### Étape 3 — Remplacer le bruit des buts par le xG quand c'est possible

Un 1-0 peut cacher une domination stérile comme un hold-up. Pour chaque match,
le moteur construit une valeur de buts plus stable :

```
si xG saisi               : valeur = xG
sinon si tirs cadrés      : valeur = min(0,30 × tirs cadrés ; 4,0)
sinon                     : valeur = buts réels
```

Puis il mélange buts et xG :

```
valeur_attaque = (1 − w) × buts_pour   + w × xG_pour
valeur_défense = (1 − w) × buts_contre + w × xG_contre
```

`w = 0,50` par défaut. Concrètement, une équipe qui a 1,0 but et 2,0 xG est
traitée comme une attaque à 1,5, pas comme une attaque à 1,0.

Deux garde-fous :

- si le xG manque pour un match, ce match utilise **uniquement ses buts**
  (aucune valeur inventée) ;
- le proxy par tirs cadrés est plafonné à 4,0 pour qu'un match aberrant ne
  domine pas l'échantillon.

La **couverture xG** mesure la part du poids total couverte par le xG ou le
proxy. Sous 50 %, l'interface affiche un avertissement : le modèle s'appuie
surtout sur les buts.

### Étape 4 — Estimer la force d'attaque et de défense

Le moteur calcule d'abord la moyenne de buts du championnat, par équipe et par
match, pondérée par la récence :

```
league_average = buts marqués par équipe et par match
```

Ensuite, pour chaque équipe :

```
attaque = (valeur_attaque_pondérée + 5 × league_average)
          / (poids_total + 5)
          / league_average

défense = (valeur_défense_pondérée + 5 × league_average)
          / (poids_total + 5)
          / league_average
```

Le « + 5 » est un **prior** : il tire l'estimation vers la moyenne du
championnat. Conséquence :

- une équipe avec 3 matchs ne sera jamais déclarée imbattable ;
- une équipe avec 38 matchs voit sa vraie performance dominer le prior.

Une attaque de 1,20 signifie « marque 20 % de plus que la moyenne ». Une
défense de 0,95 signifie « encaisse 5 % de moins que la moyenne ».

### Étape 5 — Estimer l'avantage du terrain

L'avantage du terrain n'est pas supposé fixe : il est mesuré sur les données,
puis régularisé.

```
facteur_domicile = moyenne_buts_domicile / league_average
facteur_extérieur = moyenne_buts_extérieur / league_average
```

Chaque facteur est ensuite tiré vers une valeur de référence (1,12 pour le
domicile, 0,90 pour l'extérieur), avec un poids de 10 matchs virtuels :

```
facteur = (facteur_observé × poids_observé + facteur_prior × league_average × 10)
          / (poids_observé + 10)
          / league_average
```

Bornes : domicile entre 0,85 et 1,45 ; extérieur entre 0,70 et 1,15.

### Étape 6 — Calculer les buts attendus du match

```
λ_domicile = league_average × attaque_domicile × défense_extérieur × facteur_domicile
λ_extérieur = league_average × attaque_extérieur × défense_domicile × facteur_extérieur
```

Chaque λ est borné entre 0,05 et 6,0 buts. C'est le cœur du modèle : deux
forces qui s'affrontent produisent un nombre de buts attendus pour chaque camp.

### Étape 7 — Estimer rho (correction Dixon-Coles)

Le modèle de Poisson simple sous-estime les 0-0 et 1-1, et surestime les 1-0 et
0-1. `rho` corrige ces quatre scores.

Le moteur :

1. construit les moyennes de buts domicile / extérieur du bassin de matchs ;
2. essaie toutes les valeurs de `rho` entre **−0,20 et +0,15**, par pas de
   0,005 ;
3. garde celle qui rend les scores réellement observés les plus probables
   (vraisemblance logarithmique pondérée) ;
4. la tire vers le prior **−0,05** avec un poids de 30 matchs :

```
rho_final = (n_eff × rho_observé + 30 × (−0,05)) / (n_eff + 30)
```

- petit historique → `rho` proche de −0,05 ;
- historique long → `rho` laisse parler les données ;
- `rho` reste toujours dans [−0,20 ; +0,15].

Un `rho` négatif renforce légèrement les 0-0 et 1-1, et réduit les 1-0 et 0-1.

### Étape 8 — Construire la matrice des scores

Le moteur combine deux lois de Poisson indépendantes :

```
P(score = i-j) = P(i buts domicile) × P(j buts extérieur)
```

Puis il applique la correction Dixon-Coles aux quatre scores serrés :

```
P(0-0) ← P(0-0) × (1 − λ_dom × λ_ext × rho)
P(0-1) ← P(0-1) × (1 + λ_dom × rho)
P(1-0) ← P(1-0) × (1 + λ_ext × rho)
P(1-1) ← P(1-1) × (1 − rho)
```

Les valeurs négatives sont ramenées à zéro, puis **toute la matrice est
renormalisée** pour que la somme des probabilités vaille exactement 1.

La matrice va de 0 à 10 buts par équipe (11 × 11 = 121 scores). Au-delà de
10 buts, la probabilité est négligeable et ignorée.

### Étape 9 — Déduire tous les marchés

À partir de cette unique matrice :

| Marché | Calcul |
|---|---|
| **1** (domicile gagne) | somme des cases où buts domicile > buts extérieur |
| **X** (nul) | somme de la diagonale |
| **2** (extérieur gagne) | somme des cases où buts domicile < buts extérieur |
| **1X, 12, X2** | sommes des issues correspondantes |
| **Plus de 2,5** | somme des cases où total de buts > 2,5 |
| **Moins de 2,5** | somme des cases où total de buts < 2,5 |
| **Remboursement** | somme des cases où total = ligne (utile pour les lignes entières) |
| **BTTS oui** | somme des cases où les deux équipes marquent au moins 1 but |
| **Scores exacts** | les 8 cases les plus probables |

C'est pour cela que tous les marchés sont **cohérents entre eux** : ils sortent
du même tableau, pas de calculs séparés.

### Étape 10 — Évaluer la qualité de l'échantillon

Le niveau de qualité dépend du plus petit nombre de matchs effectifs des deux
équipes :

| Matchs effectifs | Niveau |
|---|---|
| moins de 5 | Très faible |
| 5 à 9 | Faible |
| 10 à 19 | Moyenne |
| 20 à 29 | Correcte |
| 30 et plus | Bonne |

L'interface ajoute des avertissements si :

- l'échantillon effectif est inférieur à 10 ;
- une équipe a moins de 5 matchs pris en compte ;
- le dernier match pris en compte date de plus de 90 jours ;
- l'historique mélange plusieurs compétitions ;
- le xG/proxy couvre moins de 50 % des matchs ;
- aucune statistique xG ni tir cadré n'est disponible.

---

## 4. Un exemple chiffré complet

Exemple synthétique, avec des valeurs rondes pour suivre le calcul.

**Données du problème :**

```
league_average        = 1,35 but par équipe et par match
attaque_domicile      = 1,20
défense_extérieur     = 1,10
facteur_domicile      = 1,15
attaque_extérieur     = 0,90
défense_domicile      = 0,95
facteur_extérieur     = 0,92
rho                   = −0,05
```

**Buts attendus :**

```
λ_domicile = 1,35 × 1,20 × 1,10 × 1,15 = 2,05
λ_extérieur = 1,35 × 0,90 × 0,95 × 0,92 = 1,06
```

**Résultat de la matrice (avec ces paramètres) :**

| Marché | Probabilité |
|---|---|
| 1 (domicile) | 59,7 % |
| X (nul) | 21,9 % |
| 2 (extérieur) | 18,4 % |
| 1X | 81,6 % |
| 12 | 78,2 % |
| X2 | 40,3 % |
| Plus de 1,5 but | 82,2 % |
| Plus de 2,5 buts | 60,1 % |
| Moins de 3,5 buts | 62,3 % |
| BTTS oui | 57,4 % |
| BTTS non | 42,6 % |

Les scores exacts les plus probables :

| Score | Probabilité |
|---|---|
| 1-1 | 10,2 % |
| 2-1 | 9,9 % |
| 2-0 | 9,4 % |
| 1-0 | 8,7 % |
| 3-1 | 6,8 % |

**Lecture :** le modèle « voit » un match légèrement dominé par le domicile,
avec beaucoup de buts. Il ne dit pas que le domicile va gagner : il dit que,
dans son modèle, ce résultat arrive environ 6 fois sur 10.

---

## 5. Les fourchettes d'incertitude

Les forces estimées ne sont pas exactes : elles dépendent de l'échantillon.
Le moteur le reconnaît explicitement.

### La simulation

1. Il tire **1 000 scénarios** de forces possibles.
2. Chaque force est multipliée par un facteur log-normal :
   - facteur global du championnat : écart-type 0,05 ;
   - bonus domicile : écart-type 0,04 ;
   - attaque/défense de chaque équipe : écart-type
     `1 / √(matchs effectifs)`, borné entre 0,08 et 0,85.
3. Pour chaque scénario, il recalcule λ domicile, λ extérieur, la matrice et
   tous les marchés.
4. Il garde les **percentiles 10, 50 et 90**.

La fourchette affichée est donc :

```
[percentile 10 ; percentile 90]
```

Elle contient 80 % des scénarios simulés. Plus l'échantillon est petit, plus
elle est large.

### Deux précautions

- **La graine est fixe** (`20261108`) : les mêmes données donnent exactement les
  mêmes fourchettes. Ce n'est pas un tirage aléatoire à chaque affichage.
- **La fourchette est élargie si nécessaire** pour inclure la probabilité
  ponctuelle. Une probabilité ne peut jamais sortir de son propre intervalle.

> Une fourchette large n'est pas un défaut : c'est le modèle qui avoue son
> incertitude. Une fourchette étroite sur 3 matchs serait au contraire
> trompeuse.

---

## 6. Le générateur de combinaisons

Le générateur ne calcule aucune probabilité : il **réutilise** celles du moteur
et cherche des assemblages de cotes.

### 6.1 Ce qu'il reçoit

- vos préférences : nombre de sélections (8 par défaut), cote min (50), cote
  max (100), marchés autorisés, demi-vie, taille d'historique ;
- les paramètres du formulaire, qui peuvent les remplacer ponctuellement sans
  modifier les préférences enregistrées.

Marchés autorisés :

| Code | Marchés |
|---|---|
| `1X2` | Résultat du match |
| `DOUBLE_CHANCE` | 1X, 12, X2 |
| `PLUS_MOINS` | Totaux 1,5 / 2,5 / 3,5 |
| `BTTS` | Les deux équipes marquent |

### 6.2 Il choisit d'abord un jour

C'est une règle importante, ajoutée en Phase 12.

1. Il charge les rencontres **programmées**, en football, dont le coup d'envoi
   est **futur**, triées par date. Plafond : les **50 premières**.
2. Il regroupe ces rencontres par **jour calendaire Europe/Paris**.
3. Il cherche le **premier jour** qui contient au moins une rencontre avec une
   cote exploitable (au moins un relevé dans un marché autorisé).
4. S'il n'y en a aucun, il prend le premier jour contenant des rencontres,
   même sans cote, pour pouvoir expliquer pourquoi il n'y a rien à proposer.

Conséquences :

- une combinaison ne mélange **jamais** deux jours différents ;
- si aujourd'hui n'a pas de cote mais demain en a, le générateur travaille sur
  demain et l'indique (`jour_cible`, `repli_jour = true`) ;
- « cote récente » signifie ici **le dernier relevé saisi**, sans limite d'âge.
  Un ancien relevé reste utilisé tant qu'aucun nouveau n'existe.

### 6.3 Il prépare les candidats

Pour chaque rencontre du jour cible :

1. il garde les marchés `period = match`, `subject = match`, dans une famille
   autorisée ;
2. il ignore toute sélection **sans aucun relevé de cote** ;
3. il associe chaque sélection à la probabilité correspondante du moteur :

| Marché | Clé interne | Probabilité utilisée |
|---|---|---|
| 1X2 | `1x2:1`, `1x2:X`, `1x2:2` | `prediction.resultat` |
| Double chance | `double_chance:1X`, etc. | `prediction.double_chance` |
| Totaux | `total:2.5:plus`, etc. | ligne 1,5 / 2,5 / 3,5 du moteur |
| BTTS | `btts:oui`, `btts:non` | `prediction.btts` |

4. il **déduplique** : pour une même rencontre et une même probabilité du
   modèle, seule la cote la plus récente est conservée (à date égale, la cote
   la plus haute).

Une rencontre dont l'historique est insuffisant (< 3 matchs par équipe) est
écartée et comptée dans `matchs_ignores`. Aucune probabilité n'est inventée.

### 6.4 Il cherche les combinaisons

Règles :

- exactement **N sélections** (2 à 15) ;
- **au plus une sélection par rencontre** — deux sélections du même match
  seraient corrélées et fausseraient le produit des probabilités ;
- le **produit des cotes** doit tomber entre `cote_min` et `cote_max`.

L'algorithme est une **recherche en profondeur avec élagage** :

```
à chaque rencontre : choisir une sélection, ou sauter la rencontre
si le nombre de rencontres restantes ne suffit plus → arrêt
si la cote courante dépasse le maximum → arrêt
si même les meilleures cotes restantes ne suffisent pas → arrêt
si même les plus petites cotes restantes dépassent le maximum → arrêt
```

Deux limites de sécurité :

- **200 000 nœuds** explorés au maximum ;
- **5 000** combinaisons conservées en mémoire au maximum.

Si la limite de nœuds est atteinte, `recherche_tronquee` passe à `true` :
le résultat reste valable, mais il n'a pas exploré absolument tout l'espace.

### 6.5 Il classe les résultats

Pour chaque combinaison trouvée :

```
cote_totale   = produit des cotes
probabilité   = produit des probabilités estimées
fourchette    = produit des bornes basses / hautes
espérance     = probabilité × cote_totale − 1
```

Puis il classe par :

1. **espérance décroissante** ;
2. à égalité, **probabilité décroissante** ;
3. à égalité, **proximité du milieu de la fourchette** de cotes
   `(cote_min + cote_max) / 2`.

Il renvoie les `limite` meilleures (10 par défaut, 50 au maximum).

> **Pourquoi l'espérance est souvent négative ?** Parce que les cotes
> contiennent la marge du bookmaker. Une combinaison à espérance négative n'est
> pas « mauvaise » au sens du modèle : elle est simplement défavorable à long
> terme si les probabilités estimées sont justes.

### 6.6 Exemple de calcul

Deux rencontres distinctes, deux sélections :

| Sélection | Probabilité | Fourchette | Cote |
|---|---|---|---|
| A : domicile gagne | 0,60 | [0,52 ; 0,68] | 1,60 |
| B : BTTS oui | 0,55 | [0,47 ; 0,63] | 1,75 |

```
cote_totale   = 1,60 × 1,75 = 2,80
probabilité   = 0,60 × 0,55 = 0,33  (33 %)
fourchette    = [0,52 × 0,47 ; 0,68 × 0,63] = [0,244 ; 0,428]
espérance     = 0,33 × 2,80 − 1 = −0,076
```

Traduction : dans le modèle, cette combinaison a environ **33 % de chances** de
passer, pour une cote de **2,80**. Miser 1 unité rapporte 2,80 unités en cas de
réussite, mais l'espérance est de **−0,076 unité** par mise : sur un très grand
nombre de répétitions, ce type de combinaison perd en moyenne 7,6 % de la mise.

La fourchette `[24,4 % ; 42,8 %]` rappelle que cette probabilité de 33 % n'est
pas connue au point de pourcentage près.

---

## 7. Pourquoi certaines combinaisons n'apparaissent pas

Le générateur est volontairement strict. Voici les causes, dans l'ordre où le
service les vérifie.

| Situation | Ce que vous voyez | Cause |
|---|---|---|
| Aucune rencontre à venir | « Aucune rencontre à venir n'est enregistrée. » | Aucun match `programme` avec une date future. |
| Jour sans cote | « Aucune rencontre du … ne réunit une cote récente et un historique suffisant. » | Les matchs du jour existent, mais aucun n'a de cote ou assez d'historique. |
| Trop peu de rencontres exploitables | « N rencontre(s) exploitable(s) pour M sélections demandées… » | Par exemple 1 rencontre cotée pour une combinaison à 2 sélections. |
| Fourchette impossible | « Aucune combinaison de M sélections ne tombe entre 50 et 100… » | Les cotes réelles ne permettent pas d'atteindre la fourchette. |
| Aucun marché autorisé | « Aucun marché autorisé… » | Tous les marchés ont été désactivés. |
| Cote min ≥ cote max | Erreur de validation | La fourchette est incohérente. |

**Le cas le plus fréquent :** une seule rencontre cotée ne peut pas produire
une combinaison à 2 sélections, puisqu'il faut deux rencontres différentes.
Il faut soit ajouter des cotes à d'autres matchs du même jour, soit réduire le
nombre de sélections.

Autre point : le générateur ne mélange pas les jours. Si le 20 a des cotes et
le 21 aussi, une combinaison à 2 sélections ne prendra pas une sélection le 20
et une le 21. Il faut que le **même jour** contienne assez de rencontres cotées.

---

## 8. Garanties, limites et réglages

### 8.1 Ce que le système garantit

- **Reproductibilité** : mêmes données + mêmes paramètres = mêmes résultats.
  La graine des simulations est fixe.
- **Absence de fuite temporelle** : seuls les matchs terminés avant le coup
  d'envoi sont utilisés.
- **Cohérence des marchés** : tous dérivent de la même matrice de scores.
- **Traçabilité** : chaque probabilité est accompagnée d'une fourchette, d'un
  niveau de qualité et d'avertissements.
- **Aucune invention** : pas de xG → buts réels ; pas d'historique → aucune
  prédiction ; pas de cote → aucune sélection.

### 8.2 Ce que le modèle ne fait pas

- Il **n'apprend pas** automatiquement : pas de machine learning, pas de
  réentraînement nocturne.
- Il **ignore** les compositions, blessures, suspensions, cartons, météo,
  enjeu sportif, calendrier européen et mouvements de cotes.
- Il **ne mélange pas** plusieurs sports : il est football uniquement.
- Il **ne place aucun pari** et ne se connecte à aucun bookmaker.
- Il **ne prédit pas** un score exact comme s'il était certain : les scores
  exacts sont les cases les plus probables d'une distribution.
- Il suppose les **rencontres indépendantes** entre elles. C'est acceptable
  pour des matchs différents, mais imparfait si plusieurs sélections dépendent
  du même contexte (même journée, même enjeu).

### 8.3 Les réglages qui changent le plus le résultat

| Réglage | Effet d'augmenter la valeur | Effet de diminuer la valeur |
|---|---|---|
| **Demi-vie** (240 j) | Historique plus stable, moins réactif | Modèle plus réactif, plus bruité |
| **Matchs par équipe** (38) | Plus de données, plus de stabilité | Moins de données, fourchettes plus larges |
| **Poids du xG** (0,50) | Plus de poids aux occasions qu'aux buts | Plus de poids au score réel |
| **Cote min / max** (50 / 100) | Combinaisons plus longues, plus risquées | Combinaisons plus courtes, plus probables |
| **Sélections** (8) | Cote totale plus élevée, probabilité plus faible | Cote plus basse, probabilité plus élevée |

Le nombre de sélections et la fourchette de cotes interagissent fortement :
avec 8 sélections, atteindre 50–100 demande des cotes moyennes assez élevées ;
avec 3 sélections, il faut des cotes beaucoup plus fortes.

### 8.4 Comment lire une combinaison dans l'interface

| Champ | Signification |
|---|---|
| `total_odds` | Produit des cotes des sélections |
| `probability` | Produit des probabilités estimées |
| `low` / `high` | Produit des bornes basses / hautes |
| `expected_value` | `probability × total_odds − 1`, en unité de mise |
| `message` | Explication du résultat, y compris le jour choisi |
| `jour_cible` | Jour réellement analysé |
| `repli_jour` | `true` si ce n'est pas aujourd'hui |
| `matchs_examines` | Nombre de rencontres du jour cible |
| `matchs_disponibles` | Nombre de rencontres ayant produit des candidats |
| `matchs_ignores` | Rencontres sans cote ou sans historique suffisant |
| `selections_disponibles` | Nombre total de sélections candidates |
| `recherche_tronquee` | `true` si la limite de nœuds a été atteinte |

---

## 9. Où se trouve le code

| Fichier | Rôle |
|---|---|
| `apps/api/engine/__init__.py` | Rappel de la contrainte : moteur pur, aucune dépendance applicative |
| `apps/api/engine/ratings.py` | Pondération, xG/proxy, forces, avantage terrain, λ, qualité |
| `apps/api/engine/models/poisson.py` | Matrice de scores et correction Dixon-Coles |
| `apps/api/engine/models/rho.py` | Estimation de `rho` par vraisemblance |
| `apps/api/engine/markets/football.py` | Dérivation des marchés depuis la matrice |
| `apps/api/engine/uncertainty.py` | Simulations Monte Carlo et percentiles |
| `apps/api/engine/prediction.py` | Orchestration du moteur V2 |
| `apps/api/engine/combos/generator.py` | Recherche combinatoire pure |
| `apps/api/engine/settlement/__init__.py` | Règlement des sélections et combinaisons |
| `apps/api/engine/calibration/__init__.py` | Rétro-test et indicateurs de calibration |
| `apps/api/engine/odds.py` | Cotes, probabilités implicites, marge |
| `apps/api/app/services/predictions.py` | Chargement de l'historique et sérialisation |
| `apps/api/app/services/combinations.py` | Choix du jour, candidats, appel du générateur |
| `apps/api/app/services/markets.py` | Dernier relevé de cote (`latest_snapshot`) |

### Documents liés

- `docs/phases/phase-3-moteur-statistique.md` : moteur v1, bases du Poisson.
- `docs/phases/phase-4-generateur-combinaisons.md` : décisions du générateur.
- `docs/phases/phase-6-moteur-statistique-v2.md` : xG, proxy, `rho`, calibration.
- `docs/phases/phase-10-btts.md` : marché « les deux équipes marquent ».
- `docs/phases/phase-12-combinaisons-du-jour.md` : limitation au jour cible.
- `docs/phases/phase-13-cotes-liste-rencontres.md` : cotes 1X2 dans la liste.
- `docs/guide-utilisation.md` : mode d'emploi pas à pas.

---

## En une phrase

Le moteur V2 transforme votre historique en une **matrice de probabilités de
scores**, dont il déduit tous les marchés avec une fourchette d'incertitude ; le
générateur choisit ensuite, **pour un seul jour**, les assemblages de
sélections dont le produit des cotes tombe dans votre fourchette, en classant
par espérance — sans jamais promettre un résultat.

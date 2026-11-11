# Guide d'utilisation — de l'installation à la génération des combinaisons

> **ODDS ANALYST est un outil d'analyse statistique.**
> Il ne prédit pas l'issue d'une rencontre, ne garantit aucun résultat et ne
> place aucun pari. Les cotes élevées impliquent un risque élevé de perte
> totale. Chaque probabilité affichée est une estimation accompagnée d'une
> fourchette d'incertitude.

Ce guide décrit le parcours complet, écran par écran, jusqu'à la génération des
combinaisons. Les libellés entre guillemets sont ceux que vous voyez dans
l'interface.

---

## 1. À quoi sert ODDS ANALYST

L'application réunit trois choses :

1. **Un référentiel** : compétitions, saisons, équipes et rencontres.
2. **Un historique** : résultats passés, statistiques d'équipe et cotes saisies.
3. **Un moteur statistique** : il estime des probabilités pour chaque marché,
   puis assemble des sélections dont la cote totale tombe dans une fourchette
   visée.

Le générateur ne choisit pas « les meilleurs paris ». Il cherche des
combinaisons **cohérentes avec vos critères** (nombre de sélections, cote totale
visée, marchés autorisés) et affiche, pour chacune, sa probabilité estimée, sa
fourchette et son espérance. C'est un outil d'aide à la décision, pas une
recommandation de mise.

### Ce que l'application ne fait pas

- Elle ne place aucun pari et ne se connecte à aucun compte de bookmaker.
- Elle ne stocke aucun identifiant de bookmaker.
- Elle n'effectue aucun scraping non autorisé.
- Elle ne garantit aucune probabilité et ne couvre que le **football**.
- Elle n'utilise ni compositions, ni blessures, ni enjeu sportif.

---

## 2. Démarrer et se connecter

### Lancer l'application

Dans le dossier du projet :

```powershell
powershell -ExecutionPolicy Bypass -File infra/scripts/dev.ps1
```

| Service | Adresse |
|---|---|
| Interface | http://localhost:3100 |
| API (technique) | http://localhost:8000 |
| Documentation technique de l'API | http://localhost:8000/docs |

Laissez la fenêtre ouverte pendant toute la session.

### Première utilisation

À la première ouverture, l'écran « Première utilisation » crée **l'unique compte
administrateur** :

- « Adresse électronique » ;
- « Mot de passe » : au moins **12 caractères**, pas uniquement des chiffres,
  au moins 4 caractères distincts ;
- « Confirmation du mot de passe ».

Cliquez sur « Créer le compte et se connecter ». Cette étape n'est possible
qu'une seule fois.

### Connexion habituelle

Saisissez votre adresse et votre mot de passe, puis « Se connecter ».

- Cinq tentatives échouées bloquent la connexion environ 15 minutes.
- La session se ferme après 12 heures sans activité, et au plus tard 24 heures
  après la connexion.
- Il n'y a pas de « mot de passe oublié » : le compte est unique et local.

### Repères de navigation

| Page | Rôle |
|---|---|
| « Tableau de bord » | Vue d'ensemble et prochaines rencontres |
| « Compétitions » | Compétitions et saisons |
| « Connecteurs » | Imports (calendrier, résultats, statistiques, cotes) |
| « Équipes » | Référentiel des équipes |
| « Rencontres » | Création des rencontres, statistiques et résultats |
| « Combinaisons » | Génération et enregistrement des combinaisons |
| « Historique » | Combinaisons enregistrées et performance |
| « Calibration » | Rétro-test du modèle |
| « Paramètres » | Valeurs par défaut du moteur et du générateur |

---

## 3. Le parcours recommandé en un coup d'œil

```
Compétition + saison
        ↓
      Équipes
        ↓
Rencontres à venir  ──────────────┐
        ↓                         │
Historique (résultats + stats)    │  (cotes)
        ↓                         │
Pronostic de la rencontre  ←──────┘
        ↓
Génération des combinaisons
        ↓
Enregistrement dans l'historique
```

| Ordre | Action | Page |
|---|---|---|
| 1 | Créer une compétition et au moins une saison | Compétitions |
| 2 | Créer les équipes | Équipes |
| 3 | Créer les rencontres à venir | Rencontres |
| 4 | Renseigner les résultats passés (manuel ou import) | Rencontres / Connecteurs |
| 5 | Saisir les cotes récentes (manuel ou The Odds API) | Fiche rencontre / Connecteurs |
| 6 | Vérifier le pronostic et sa fiabilité | Fiche rencontre |
| 7 | Générer les combinaisons | Combinaisons |
| 8 | Enregistrer celles que vous voulez suivre | Combinaisons → Historique |

> **Règle d'or** : sans résultats passés, pas de pronostic ; sans pronostic et
> sans cote, pas de combinaison. Le générateur ignore les rencontres
> incomplètes et les compte dans « ignorée(s) ».

---

## 4. Étape 1 — Créer la compétition et la saison

Page « Compétitions ».

### Créer la compétition

Section « Nouvelle compétition » :

1. « Sport » : choisissez « Football » (seul sport réellement calculé).
2. « Nom » : par exemple « Ligue 1 ».
3. « Pays » (facultatif) : « France ».
4. « Niveau » (facultatif) : 1 pour l'élite.
5. Cliquez sur « Ajouter ».

Message attendu : « Compétition créée. »

### Ajouter une saison

1. Sur la ligne de la compétition, cliquez sur « Saisons ».
2. Renseignez « Libellé » : par exemple « 2026-2027 ».
3. « Début » et « Fin » sont facultatifs mais utiles.
4. Cliquez sur « Ajouter la saison ».

Message attendu : « Saison ajoutée. »

> **Sans saison, aucune rencontre ne peut être créée.** Si la liste des saisons
> est vide, le message « Aucune saison : ajoutez-en une pour pouvoir créer des
> rencontres. » s'affiche.

---

## 5. Étape 2 — Créer les équipes

Page « Équipes ».

Section « Nouvelle équipe » :

1. « Sport » : « Football ».
2. « Nom » : nom complet, par exemple « Paris Saint-Germain ».
3. « Nom court » (facultatif) : « PSG ».
4. « Pays » (facultatif) : « France ».
5. Cliquez sur « Ajouter ».

Message attendu : « Équipe créée. »

Bonnes pratiques :

- Utilisez **le même nom** que vos sources d'import (CSV, The Odds API) autant
  que possible.
- Un nom court aide à la lecture, mais ne sert pas à l'appariement.
- Un doublon de nom dans le même sport est refusé.
- Une équipe ne peut pas être supprimée si elle figure dans une rencontre.

Il faut au moins **deux équipes de football** pour créer une rencontre.

---

## 6. Étape 3 — Créer les rencontres à venir

Page « Rencontres ».

Section « Nouvelle rencontre » :

1. « Compétition ».
2. « Saison » : la première saison est présélectionnée.
3. « Équipe à domicile ».
4. « Équipe à l'extérieur ».
5. « Date et heure » : date et heure de coup d'envoi (heure de Paris).
6. « Stade » et « Arbitre » (facultatifs).
7. Cliquez sur « Ajouter la rencontre ».

La rencontre est créée au statut « Programmé ». C'est ce statut, avec une date
future, que le générateur utilise.

> **Vérifiez la date et l'heure.** Elles déterminent quels matchs passés entrent
> dans l'analyse : seuls les matchs **terminés avant** ce coup d'envoi sont pris
> en compte. Une date erronée fausse le pronostic.

Répétez l'opération pour toutes les rencontres à venir que vous voulez pouvoir
combiner. Le générateur examine au maximum les **50 prochaines rencontres**
programmées.

---

## 7. Étape 4 — Construire l'historique (résultats passés)

Le modèle a besoin de **matchs terminés avant la rencontre analysée**. Il exige
au minimum **3 matchs terminés par équipe** ; en dessous, il refuse de produire
une probabilité. En pratique, visez au moins **10 matchs par équipe** pour une
analyse plus stable.

Deux méthodes, cumulables.

### 7.1 Saisie manuelle (secours et correction)

1. Ouvrez la fiche d'une rencontre passée.
2. Dans « Informations et résultat », choisissez « Statut » = « Terminé ».
3. Renseignez « Score domicile », « Score extérieur » et, si vous les avez, les
   scores de mi-temps.
4. Cliquez sur « Enregistrer la rencontre ».

La rencontre entre alors dans l'historique. Ses statistiques sont facultatives,
mais elles améliorent le modèle :

- « Buts pour », « Buts contre » ;
- « Tirs », « Tirs cadrés » ;
- « Possession (%) », « Corners », « Cartons jaunes », « Cartons rouges » ;
- « Buts attendus (xG) ».

Les champs laissés vides sont ignorés ; aucune valeur n'est inventée.

### 7.2 Import du calendrier et des résultats

Page « Connecteurs ». L'ordre conseillé est : **calendrier → résultats et
statistiques → cotes**.

1. Panneau « Assistant de lien » :
   - « Fournisseur » : football-data.org (calendrier et résultats) ou
     BigBallsData ;
   - « Compétition interne » et « Saison interne » : votre compétition ;
   - « Identifiant externe » : utilisez « Découvrir » pour choisir la
     compétition chez le fournisseur ;
   - « Saison externe » : l'année de début, par exemple « 2026 » ;
   - cliquez sur « Créer le lien ».
2. Sur le lien créé, cliquez sur « Gérer ».
3. Lancez l'aperçu proposé (« Aperçu du calendrier » ou équivalent).
4. Lisez les compteurs et les avertissements.
5. Cliquez sur « Appliquer l'aperçu » avant expiration (2 heures).

> Un aperçu **n'écrit rien** : il prépare un plan que vous validez. Un aperçu
> expiré doit être relancé.

### 7.3 Import des statistiques (football-data.co.uk, gratuit)

Ce connecteur remplit les résultats et les statistiques présentes dans le
fichier public : tirs, tirs cadrés, corners, cartons et, lorsque la division les
fournit, les buts attendus (xG). Il ne demande **aucune clé**, ne consomme
**aucun quota** et **n'importe aucune cote**.

Prérequis : les rencontres doivent déjà exister dans votre calendrier interne.

1. « Assistant de lien » :
   - « Fournisseur » : « football-data.co.uk (CSV) » ;
   - « Compétition interne » et « Saison interne » ;
   - « Identifiant externe » : un code de division, par exemple `F1` pour la
     Ligue 1, `F2` pour la Ligue 2, `E0` pour la Premier League ;
   - « Saison externe » : l'année de début, par exemple « 2026 » ;
   - « Créer le lien ».
2. « Gérer » puis « Aperçu du fichier ».
3. Si des équipes ne sont pas reconnues, utilisez la liste « Choisir une
   équipe… » et le bouton « Associer » pour chaque nom signalé. L'association est
   mémorisée.
4. Relisez les compteurs : « reçues », « créées », « mises à jour »,
   « inchangées », « conflits », « ignorées ».
5. Cliquez sur « Appliquer l'aperçu ».

Points importants :

- Les valeurs saisies à la main ne sont **jamais écrasées** : un désaccord est
  compté en « conflit » et conservé.
- Les rencontres du fichier absentes de votre calendrier sont « ignorées » :
  importez d'abord le calendrier, puis relancez l'aperçu.
- L'aperçu expire au bout de 2 heures.

### 7.4 Vérifier que l'historique est suffisant

Ouvrez une rencontre à venir et regardez « Analyse statistique (modèle v2) » :

- si le pronostic s'affiche, l'historique est suffisant ;
- sinon, le message indique combien de matchs chaque équipe possède et combien
  il en faut.

Ajoutez les résultats manquants, puis cliquez sur « Actualiser ».

---

## 8. Étape 5 — Saisir les cotes

Le générateur a besoin d'une cote récente pour chaque sélection qu'il utilise.
Deux méthodes.

### 8.1 Saisie manuelle, rencontre par rencontre

1. Ouvrez la fiche de la rencontre.
2. Panneau « Marchés et cotes (N) ».
3. Choisissez un modèle dans « Marché du catalogue » :
   - « Résultat (temps réglementaire) » : « Domicile », « Match nul »,
     « Extérieur » ;
   - « Double chance » : « Domicile ou nul », « Domicile ou extérieur »,
     « Nul ou extérieur » ;
   - « Total de buts » : renseignez « Ligne » (par exemple 2,5), puis
     « Plus » / « Moins » ;
   - « Les deux équipes marquent » : « Oui » / « Non ».
4. Renseignez chaque « Cote » (cote décimale, strictement supérieure à 1 ; la
   virgule est acceptée : `2,10`).
5. Cliquez sur « Ajouter le marché ».

Une cote peut rester vide à la création du marché : elle sera simplement
ignorée par le générateur tant qu'aucun relevé n'existe.

Messages attendus :

- « Marché ajouté. Saisissez une nouvelle cote quand elle évolue. »
- « Chaque cote doit être strictement supérieure à 1. »
- « Ce marché nécessite une ligne (par exemple 2,5 buts). »

Ensuite, quand la cote évolue :

1. Dans la carte du marché, saisissez la valeur dans « Nouvelle cote ».
2. Cliquez sur « Ajouter ».
3. L'ancienne cote reste dans « Historique (N) » : **aucune cote n'est
   écrasée**.

Pour corriger une erreur :

- nouvelle cote erronée : ajoutez la bonne valeur, elle devient la cote
  affichée ;
- relevé précis erroné : ouvrez « Historique (N) » et cliquez sur « × »
  (l'historique affiché est limité aux 10 relevés les plus récents) ;
- marché entier erroné : supprimez le marché et recréez-le.

> **Marchés réellement utilisés par le générateur** : 1X2, double chance,
> plus / moins de buts et « les deux équipes marquent ». Les autres marchés
> (corners, cartons, joueurs, mi-temps…) restent disponibles pour l'analyse et
> la saisie, mais ne produisent pas de sélections dans les combinaisons.
>
> Pour les totaux, le modèle fournit les lignes **1,5 / 2,5 / 3,5 buts**. Une
> cote sur une autre ligne (4,5 par exemple) n'est pas utilisée par le
> générateur.
>
> Pour « les deux équipes marquent », le marché du catalogue s'appelle
> exactement « Les deux équipes marquent », avec les issues « Oui » et « Non ».

### 8.2 Import des cotes 1xBet via The Odds API

Page « Connecteurs ».

1. « Assistant de lien » :
   - « Fournisseur » : « The Odds API (cotes 1xBet) » ;
   - « Compétition interne » et « Saison interne » ;
   - « Identifiant externe » : la clé de sport, par exemple
     `soccer_france_ligue_one` (bouton « Découvrir » pour la trouver) ;
   - « Saison externe » : par exemple « 2026 » ;
   - « Créer le lien ».
2. « Gérer » puis « Apparier (gratuit) » :
   - les événements déjà associés sont comptés ;
   - les événements non associés s'affichent : choisissez la rencontre interne
     dans « Choisir une rencontre… », puis « Associer ».
3. « Aperçu (2 crédits) » pour les cotes principales (1X2 et totaux).
4. Relisez les avertissements et les compteurs, puis « Appliquer les cotes ».
5. Pour la double chance et « les deux équipes marquent » : cochez jusqu'à
   **20 événements** déjà appariés, puis « Aperçu (N crédits) » et
   « Appliquer les marchés étendus ».

À savoir :

- L'appariement est **gratuit** ; un aperçu de cotes coûte **2 crédits** ;
  les marchés étendus coûtent **2 crédits par rencontre**.
- Le quota est **mensuel** (400 crédits par défaut) et affiché dans « État des
  fournisseurs » et dans le « Journal des synchronisations ».
- Seul **1xBet** est utilisé. Si 1xBet est absent, aucune cote n'est importée et
  aucun autre bookmaker ne le remplace.
- Un événement est associé automatiquement si une **seule** rencontre
  correspond, à **±30 minutes** du coup d'envoi, avec les deux mêmes équipes.
  Sinon, vous associez à la main : l'association est mémorisée.
- Un aperçu expire au bout de 2 heures.
- Les cotes importées doivent être strictement supérieures à 1,01 et
  strictement inférieures à 1000.

### 8.3 Ce qu'affiche une cote enregistrée

Pour chaque marché :

- la cote la plus récente et la date du dernier relevé ;
- « Implicite X % » : probabilité implicite de la cote (1 / cote) ;
- « équitable Y » : cote recalculée après retrait de la marge du bookmaker ;
- un badge « Marge X % », « Cotes incomplètes » ou « Cotes incohérentes » ;
- « Historique (N) » : les derniers relevés.

Une somme des probabilités implicites **supérieure à 100 %** est normale : c'est
la marge du bookmaker. **Inférieure à 100 %**, elle signale une saisie
incomplète ou incohérente.

---

## 9. Étape 6 — Vérifier le pronostic avant de générer

Ouvrez la fiche d'une rencontre à venir et lisez « Analyse statistique
(modèle v2) ».

### Ce qu'il faut regarder

1. **La fiabilité** : badge « Fiabilité très faible », « faible », « moyenne »,
   « correcte » ou « bonne », avec le nombre de matchs pris en compte et
   l'échantillon effectif.
2. **Les avertissements** : échantillon faible, équipe avec peu de matchs,
   dernier match ancien, plusieurs compétitions mélangées, absence de xG ou de
   tirs cadrés.
3. **Les buts attendus** : une valeur par équipe et le total attendu.
4. **Les probabilités** : 1X2, double chance, BTTS, totaux 1,5 / 2,5 / 3,5,
   scores exacts les plus probables.
5. **Les fourchettes à 80 %** : « Fourchette 80 % : X % – Y % ».

### Comment lire une fourchette

- La valeur centrale est l'estimation du modèle.
- La fourchette est un intervalle issu d'une simulation de l'incertitude des
  forces estimées : les vraies chances s'y situent *probablement*, sans
  garantie.
- Plus la fourchette est large, plus l'estimation est fragile.
- Elle ne couvre pas les événements imprévisibles : blessures, cartons,
  arbitrage, composition d'équipe.

### Si l'historique est insuffisant

Le message indique le nombre de matchs terminés de chaque équipe et le minimum
requis (3). Ajoutez des résultats passés, puis cliquez sur « Actualiser ».

> L'analyse ne dépend **pas** des cotes. Modifier une cote ne change pas les
> probabilités affichées ; elle change seulement la cote totale et l'espérance
> des combinaisons.

---

## 10. Étape 7 — Générer les combinaisons

Page « Combinaisons ».

### 10.1 Vérifications avant de lancer

| Point | Ce qu'il faut |
|---|---|
| Rencontres | Au moins autant de rencontres exploitables que de sélections demandées (2 minimum), **programmées**, à venir, en football |
| Historique | Au moins 3 matchs terminés par équipe, avant chaque coup d'envoi |
| Cotes | Une cote récente sur les sélections voulues (1X2, double chance, total 1,5/2,5/3,5, « les deux équipes marquent ») |
| Marchés | Au moins un marché coché dans le formulaire |
| Cotes du générateur | Cote minimale strictement inférieure à la cote maximale |

### 10.2 Les critères de recherche

Le panneau « Critères de recherche » est prérempli avec vos « Paramètres » :

| Champ | Rôle | Valeur initiale |
|---|---|---|
| « Sélections » | Nombre de sélections par combinaison (2 à 15) | 8 |
| « Cote minimale » | Cote totale minimale visée | 50 |
| « Cote maximale » | Cote totale maximale visée | 100 |
| « Résultats » | Nombre maximal de combinaisons affichées (5, 10, 20, 30 ou 50) | 10 |
| « Marchés autorisés » | 1X2, double chance, plus / moins de buts, les deux équipes marquent | les quatre cochés |

Modifier ces valeurs ici **ne change pas** vos préférences enregistrées : c'est
un réglage pour la recherche en cours.

### 10.3 Lancer la recherche

Cliquez sur « Générer les combinaisons » (le bouton affiche « Recherche… »
pendant le calcul).

Le bandeau « Résultat de la recherche » affiche :

- le message de synthèse ;
- le nombre de rencontres **examinées**, **exploitables**, **ignorées** ;
- le nombre de **sélections disponibles** ;
- un avertissement si la recherche a été tronquée.

### 10.4 Lire une combinaison

Chaque carte contient :

- « Combinaison N » et le nombre de sélections ;
- « Cote totale » : le produit des cotes des sélections ;
- « Probabilité estimée » : le produit des probabilités du modèle (les
  résultats sont supposés indépendants) ;
- « Fourchette 80 % » : l'incertitude cumulée ;
- « Espérance estimée » : probabilité × cote totale − 1, avec un badge vert si
  positive, rouge si négative ;
- un tableau « Rencontre / Marché / Choix / Cote / Probabilité estimée ».

Une combinaison contient **au plus une sélection par rencontre**.

### 10.5 Enregistrer une combinaison

Cliquez sur « Enregistrer dans l'historique » sous la carte voulue.

- La cote totale et les estimations sont **figées** au moment de
  l'enregistrement.
- Le bouton devient « Enregistrée » et un lien « Voir l'historique » apparaît.
- Le statut de la combinaison est recalculé ensuite à partir des scores saisis.

L'historique sert à mesurer honnêtement vos résultats (taux de réussite,
résultat net, ROI en unités de mise), pas à recommander une mise.

### 10.6 Si aucune combinaison ne s'affiche

| Message | Cause probable | Action |
|---|---|---|
| « Aucune rencontre à venir n'est enregistrée. » | Aucune rencontre future au statut « Programmé » | Créez ou importez des rencontres à venir |
| « Aucune rencontre à venir ne réunit une cote récente et un historique suffisant… » | Cotes manquantes ou historique trop court | Saisissez les cotes et les résultats passés |
| « N rencontre(s) exploitable(s) pour M sélections demandées… » | Pas assez de rencontres avec cote **et** historique suffisant | Réduisez « Sélections » ou complétez cotes et résultats |
| « Aucune combinaison de M sélections ne tombe entre X et Y… » | Fourchette trop étroite ou nombre de sélections inadapté | Élargissez « Cote minimale » / « Cote maximale » ou changez « Sélections » |
| « La recherche a atteint sa limite d'exploration… » | Trop de combinaisons possibles | Réduisez le nombre de sélections ou resserrez les critères |

Les rencontres ignorées le sont pour l'une de ces raisons : pas de cote
récente, historique insuffisant, ou aucun marché autorisé avec une cote. Ouvrez
la fiche concernée pour voir laquelle s'applique.

### 10.7 Limites à connaître

- Seul le **football** est traité.
- Seules les rencontres au statut « Programmé » et à venir sont examinées.
- Au plus **50 rencontres** sont examinées, les plus proches d'abord.
- Le générateur utilise les marchés du **match** (pas mi-temps, pas joueur).
- Une seule sélection par rencontre dans une combinaison.
- Les totaux sont limités aux lignes **1,5 / 2,5 / 3,5**.
- « Les deux équipes marquent » se règle sans remboursement possible : « Oui »
  gagne si chaque équipe marque au moins un but, « Non » sinon.
- L'espérance est calculée avec la cote saisie : une cote obsolète fausse le
  résultat.

---

## 11. Comprendre les chiffres affichés

| Terme | Définition | Piège à éviter |
|---|---|---|
| Cote décimale | Gain total pour 1 unité misée (2,10 → 2,10 unités) | Ce n'est pas une probabilité |
| Probabilité implicite | 1 / cote | Elle inclut la marge du bookmaker |
| Cote équitable | Cote après retrait de la marge | Reste une estimation, pas une vérité |
| Probabilité estimée | Sortie du modèle statistique | Ce n'est pas une garantie |
| Fourchette 80 % | Intervalle simulé autour de l'estimation | Ne couvre pas blessures et arbitrage |
| Espérance estimée | Probabilité × cote − 1 | Une espérance positive n'est pas une certitude |
| Marge | Somme des probabilités implicites − 100 % | Une somme < 100 % signale une erreur de saisie |

Exemple de lecture : une combinaison à cote 92, probabilité estimée 1,2 % et
espérance +10 % ne signifie pas « gain probable ». Cela signifie que, selon le
modèle, la cote est légèrement supérieure à ce que les probabilités suggèrent —
avec une forte incertitude et un risque élevé de perte totale.

---

## 12. Bonnes pratiques

1. **Mettez à jour les résultats après chaque journée.** Un historique qui
   s'arrête il y a trois mois produit des pronostics décalés.
2. **Rafraîchissez les cotes juste avant de générer.** Le générateur utilise le
   dernier relevé enregistré.
3. **Visez au moins 10 matchs terminés par équipe**, même si le minimum est 3.
4. **Regardez la fiabilité et les avertissements** avant de lire les
   probabilités.
5. **Complétez le xG ou les tirs cadrés** quand vous les avez : le modèle les
   préfère aux buts seuls.
6. **Élargissez progressivement la fourchette de cotes** plutôt que de forcer
   un nombre de sélections trop élevé.
7. **Enregistrez les combinaisons que vous suivez** : c'est le seul moyen de
   vérifier la calibration de vos choix.
8. **Ne traitez jamais une fourchette comme une promesse.** L'outil est
   volontairement prudent ; gardez cette prudence dans vos décisions.

---

## 13. Dépannage rapide

| Symptôme | Cause probable | Solution |
|---|---|---|
| « Historique insuffisant » | Moins de 3 matchs terminés par équipe avant le coup d'envoi | Ajoutez des résultats passés, puis « Actualiser » |
| Une rencontre n'apparaît jamais dans les combinaisons | Statut non « Programmé », date passée, sport non football, ou aucune cote sur les marchés autorisés | Vérifiez la fiche et les marchés |
| Un total saisi n'est pas utilisé | Ligne différente de 1,5 / 2,5 / 3,5 | Saisissez l'une de ces lignes |
| Peu de sélections disponibles | Marchés autorisés trop restrictifs, cotes incomplètes | Cochez plus de marchés, complétez les cotes |
| Cote affichée comme incohérente | Somme des probabilités implicites < 100 % | Vérifiez que toutes les issues sont saisies |
| Un import CSV ignore des rencontres | Calendrier interne incomplet ou équipes non associées | Importez le calendrier, associez les équipes, relancez |
| « Cet aperçu a expiré » | Plus de 2 heures entre l'aperçu et l'application | Relancez l'aperçu |
| 1xBet absent lors de l'import | Le bookmaker ne couvre pas l'événement | Aucune cote n'est importée : saisissez à la main |
| Le quota The Odds API baisse vite | Aperçus de cotes (2 crédits) et marchés étendus (2 par rencontre) | Utilisez l'appariement gratuit et limitez les aperçus |
| Connexion bloquée | Cinq échecs consécutifs | Attendez environ 15 minutes |
| Page blanche ou erreur 500 | API arrêtée ou session expirée | Relancez `dev.ps1`, puis reconnectez-vous |

---

## 14. Sécurité et confidentialité

- Toutes les données restent **sur votre machine**.
- Les clés des fournisseurs sont lues dans le fichier `.env` du serveur et ne
  sont **jamais** affichées dans l'interface ni journalisées.
- Aucun identifiant de bookmaker n'est demandé ni conservé.
- Aucun pari n'est placé automatiquement.
- Le compte est unique : protégez votre mot de passe et votre machine.

---

## 15. Aide-mémoire — la check-list avant de générer

```
[ ] Compétition + saison créées
[ ] Au moins 2 équipes de football
[ ] Au moins 2 rencontres à venir, statut « Programmé », date future
[ ] Au moins 3 matchs terminés par équipe, avec scores
[ ] Statistiques xG ou tirs cadrés saisies si disponibles
[ ] Cotes récentes sur les marchés voulus (1X2, double chance, total 1,5/2,5/3,5,
    « les deux équipes marquent »)
[ ] Paramètres : cote min < cote max, marchés cochés
[ ] Fiche rencontre : pronostic affiché et fiabilité lue
[ ] Page Combinaisons : critères choisis, puis « Générer les combinaisons »
[ ] Combinaisons intéressantes enregistrées dans l'historique
```

Pour aller plus loin :

- décisions et tests des imports : `docs/phases/phase-7-connecteurs-donnees.md` ;
- modèle statistique : `docs/phases/phase-6-moteur-statistique-v2.md` ;
- performances et appariement : `docs/phases/phase-9-appariement-performance.md` ;
- sauvegarde et dépannage : `docs/exploitation/`.

# Système de design — « Registre »

> Document de référence de l'interface ODDS ANALYST.
> Dernière mise à jour : 22 novembre 2026.

---

## 1. Intention

ODDS ANALYST est un **poste de travail d'analyse**, pas un tableau de bord
SaaS. L'interface doit aider à lire vite des rencontres, des cotes et des
probabilités, puis à décider — sans jamais suggérer qu'un résultat est certain.

Le système s'appelle **Registre** : des lignes, des colonnes, des chiffres
alignés, un seul accent. Les cartes sont réservées aux formulaires et aux
actions. Les données vivent dans des sections séparées par des filets.

### Ce que le système refuse

- le fond bleu nuit + accent cyan du tableau de bord développeur ;
- le crème + serif + terracotta des pages générées ;
- le noir + vert acide ;
- les cartes SaaS identiques, ombres douces et dégradés décoratifs ;
- les libellés en majuscules, les numéros décoratifs, les flèches ajoutées aux
  boutons.

---

## 2. Couleurs

Toutes les couleurs viennent de `apps/web/src/app/globals.css` (`@theme`).

| Jeton | Hex | Usage | Contraste |
|---|---|---|---|
| `fond` | `#0B100E` | Fond de page | — |
| `fond-panneau` | `#121A16` | Formulaires, entêtes de tableau | — |
| `fond-eleve` | `#1A241E` | Survol, champs | — |
| `bordure` | `#26332C` | Filets, séparateurs | — |
| `bordure-forte` | `#3A4A40` | Entêtes, contours de contrôle | — |
| `texte` | `#E9E6DA` | Texte principal | 14,2:1 |
| `texte-doux` | `#9AA69E` | Texte secondaire | 7,0:1 |
| `texte-faible` | `#8A968D` | Métadonnées | 5,8:1 |
| `accent` | `#E1542E` | Action, direct, attention | 4,7:1 |
| `succes` | `#4FA87C` | Résultat favorable | 6,1:1 |
| `alerte` | `#D9A441` | Avertissement | 7,9:1 |
| `danger` | `#E06A58` | Erreur, action destructive | 5,4:1 |

Règles :

1. `accent` ne sert **jamais** à deux intentions à la fois. Il signifie
   « action » ou « à regarder ».
2. Le négatif est porté par `danger` et un signe explicite, pas par une
   troisième couleur.
3. Aucune couleur codée en dur dans les pages. Les utilitaires Tailwind
   autorisés sont ceux dérivés des jetons (`text-texte-doux`, `bg-fond-panneau`,
   `border-bordure`…).
4. Les contrastes ci-dessus sont calculés sur `fond-panneau`. Toute nouvelle
   couleur doit être vérifiée avant usage.

---

## 3. Typographie

Deux familles, chargées par `next/font` :

| Famille | Rôle |
|---|---|
| **Archivo** (400/500/600) | Interface, titres, libellés |
| **IBM Plex Mono** (400/500) | Chiffres uniquement : cotes, probabilités, scores, unités, dates/heures |

Le mono est **fonctionnel** : il aligne les décimales en colonne. Il n'est
jamais utilisé pour des libellés.

### Échelle

| Taille | Usage |
|---|---|
| 11 px | Micro-libellés, entêtes de tableau |
| 12 px | Métadonnées, aides, textes secondaires |
| 14 px | Corps, boutons, champs |
| 16 px | Titre de section |
| 24 px | Titre de page |
| 32 px | Chiffre héros (score, cote principale) |

Règles :

- `font-variant-numeric: tabular-nums` est appliqué globalement.
- Les libellés sont en phrase, pas en majuscules.
- Une ligne de texte reste sous 72 caractères.
- Pas d'accent sur un seul mot d'un titre.
- Les chiffres sont alignés à droite dans les tableaux, les libellés à gauche.

---

## 4. Mise en page

### Coquille

- Barre latérale de 256 px à partir de `lg` (1024 px), groupée :
  **Référentiel**, **Analyse**, **Système**.
- En dessous de `lg`, navigation en grille (2 colonnes sur mobile, 3 sur
  tablette), sans défilement horizontal.
- Barre supérieure fine : contexte et déconnexion. Le message éthique vit dans
  le pied de page, une seule fois.
- Contenu : largeur maximale de 1152 px, padding 20 px / 32 px.

### Page

```
EntetePage
  titre 24 px
  description 14 px, 62 caractères max
  action principale à droite
──────────────────────────────────────────
Section (filet supérieur, pas de carte)
  titre 16 px
  description 12 px
  contenu
──────────────────────────────────────────
Section
```

### Registre de données

- Les listes sont des tableaux sémantiques (`table`, `th scope="col"`,
  `caption` en `sr-only`).
- Un filet sépare les lignes ; pas de fond alterné.
- La ligne survolée change de fond (`hover:bg-fond-panneau`).
- Les cotes forment un triplet visuel : `1`, `X`, `2`, alignés à droite, en
  mono, avec la cote la plus basse en gras.
- Le statut est une pastille de couleur suivie de son libellé, pas une
  pastille arrondie seule.
- Les tableaux trop larges défilent horizontalement dans leur conteneur.

### Formulaire

- Les formulaires de création sont **repliés par défaut**.
- Un formulaire ouvert est une carte `rounded-lg`, bordure `bordure`,
  fond `fond-panneau`, padding 20 px.
- Les champs sont sur une grille de 2 colonnes (mobile) à 4 colonnes (desktop).
- L'action principale est un bouton plein `accent` ; l'annulation est discrète.
- Les actions destructrices sont séparées et confirmation demandée.

### Fiche rencontre

```
← Rencontres
Équipe A  2 — 1  Équipe B         [statut]
compétition · saison · date
──────────────────────────────────────────
Section « Analyse » (pleine largeur)
Section « Marchés et cotes »
Section « Informations et résultat »   (repliable)
Section « Statistiques d'équipe »      (repliable)
```

Le match est le héros ; le formulaire d'édition ne l'est jamais.

---

## 5. Composants partagés

Dans `apps/web/src/components/ui.tsx` :

| Composant | Rôle |
|---|---|
| `EntetePage` | Titre, description, action |
| `Section` | Bloc de données avec filet supérieur |
| `Panneau` | Carte de formulaire ou d'action |
| `Indicateur` | Libellé + valeur mono + aide |
| `Tableau` | Conteneur de tableau avec défilement |
| `Bouton` | `principal`, `secondaire`, `danger`, `discret` |
| `Champ` | Libellé, aide, contrôle |
| `Saisie`, `Selection`, `ZoneTexte` | Contrôles |
| `Alerte` | Erreur, succès, info, avertissement |
| `Badge` | Étiquette courte, non arrondie |
| `EtatVide` | Absence de données, avec piste d'action |
| `Chargement` | Attente |

Règles d'usage :

- `Section` pour les données ; `Panneau` pour les formulaires.
- Une page ne contient qu'une seule action principale visible.
- Une erreur est annoncée (`role="alert"`), un succès est poli
  (`role="status"`).
- Un état vide dit quoi faire ensuite.
- Pas de composant dupliqué localement : `Indicateur`, `pourcent`, `cote` et
  les listes de marchés vivent à un seul endroit.

---

## 6. Contenu

- Écrire du point de vue de l'utilisateur : « Enregistrer la rencontre », pas
  « Soumettre ».
- Une action garde le même nom du bouton au message de confirmation.
- Les erreurs expliquent ce qui s'est passé et quoi faire.
- Le message éthique (« outil d'analyse, aucun pari automatique ») est dit
  **une fois** dans le pied de page, et rappelé uniquement là où une décision
  pourrait être mal interprétée (combinaisons, historique).
- Pas de phrases de remplissage dans les entêtes de section.

---

## 7. Accessibilité

- Contraste minimum 4,5:1 pour le texte, vérifié sur les jetons.
- Plancher typographique : 11 px pour les micro-libellés, 12 px pour le reste.
- Focus visible : contour `accent` de 2 px, décalé de 2 px.
- Cibles tactiles : 36 px de haut minimum.
- Tableaux : `caption`, `th scope="col"`, en-têtes explicites.
- Formulaires : `label` associé, aide textuelle, erreur annoncée.
- Mouvement : aucune animation décorative ; `prefers-reduced-motion` respecté
  par les transitions existantes.

---

## 8. Adoption

| Page | État |
|---|---|
| Rencontres (liste) | ✅ Pilote validé le 22/11/2026 |
| Connexion / Première utilisation | ✅ Migrée le 22/11/2026 |
| Tableau de bord | ✅ Migré le 22/11/2026 |
| Fiche rencontre | ✅ Migrée le 22/11/2026 |
| Compétitions | ✅ Migrée le 22/11/2026 |
| Équipes | ✅ Migrée le 22/11/2026 |
| Combinaisons | ✅ Migrée le 22/11/2026 |
| Historique | ✅ Migré le 22/11/2026 |
| Calibration | ✅ Migrée le 22/11/2026 |
| Paramètres | ✅ Migrés le 22/11/2026 |
| Synchronisation | ✅ Migrée le 22/11/2026 |

Les pages ont été vérifiées au build, au typage et au lint. Les états
principaux (liste, formulaire replié, états vides, connexion) ont été
contrôlés visuellement. Les états profonds de Synchronisation (rapports de
passe, imports de cotes et CSV) restent à revoir sur données réelles.

La migration est progressive : les jetons et les polices sont globaux, la mise
en page est reprise page par page.

---

## 9. Décisions

1. **Palette verte plutôt que bleue** : le vert-encre évoque le terrain et le
   registre comptable, sans reprendre le navy/cyan standard.
2. **Orange de signal** : une seule couleur d'action, lisible sur le fond et
   distincte du vert de succès.
3. **Archivo plutôt que Segoe UI** : une grotesque large, lisible en petit,
   avec un caractère sportif discret.
4. **Mono réservé aux chiffres** : l'alignement des décimales est la raison,
   pas l'esthétique « technique ».
5. **Filets plutôt que cartes** : la donnée doit dominer son conteneur.
6. **Migration page par page** : éviter une réécriture totale qui casserait
   les parcours validés.

---

## 10. Notes techniques

- Tailwind CSS 4 : les jetons sont déclarés dans `@theme`, sans fichier de
  configuration séparé.
- Polices : `next/font/google`, téléchargées au build puis servies localement.
  Pour un build hors ligne, les auto-héberger dans `apps/web/src/app/fonts/`.
- Aucune bibliothèque de composants externe.
- Les tableaux utilisent `min-w-*` et un conteneur `overflow-x-auto` ; la page
  elle-même ne défile jamais horizontalement.

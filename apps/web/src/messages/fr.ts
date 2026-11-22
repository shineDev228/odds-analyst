/**
 * Tous les libellés de l'interface sont centralisés ici.
 * L'application est en français ; ce fichier prépare une éventuelle
 * internationalisation sans en ajouter la complexité aujourd'hui.
 */

export const fr = {
  app: {
    nom: "ODDS ANALYST",
    sousTitre: "Analyse statistique sportive",
  },
  avertissement: {
    titre: "Outil d'analyse, pas de prédiction",
    texte:
      "ODDS ANALYST estime des probabilités à partir de données historiques. " +
      "Il ne prédit pas l'issue des rencontres et ne garantit aucun résultat. " +
      "Les cotes élevées impliquent un risque élevé de perte totale. " +
      "Aucun pari n'est placé automatiquement.",
  },
} as const;

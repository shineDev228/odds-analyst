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
  phases: [
    { numero: 0, libelle: "Environnement et squelette", statut: "termine" },
    { numero: 1, libelle: "Socle : authentification et rencontres", statut: "en-cours" },
    { numero: 2, libelle: "Marchés et cotes", statut: "a-venir" },
    { numero: 3, libelle: "Moteur statistique v1", statut: "a-venir" },
    { numero: 4, libelle: "Générateur de combinaisons", statut: "a-venir" },
    { numero: 5, libelle: "Historique et performance", statut: "a-venir" },
    { numero: 6, libelle: "Moteur statistique v2", statut: "a-venir" },
    { numero: 7, libelle: "Connecteurs de données", statut: "a-venir" },
    { numero: 8, libelle: "Durcissement et documentation", statut: "a-venir" },
  ],
  statuts: {
    "en-cours": "En cours",
    "a-venir": "À venir",
    termine: "Terminé",
  },
} as const;

export type StatutPhase = keyof typeof fr.statuts;

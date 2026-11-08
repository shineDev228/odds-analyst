/** Libellés français des familles, périodes et sujets de marchés. */

export const famillesMarches: Record<string, string> = {
  resultat: "Résultat",
  double_chance: "Double chance",
  handicap: "Handicaps",
  totaux: "Totaux",
  btts: "Les deux équipes marquent",
  score_exact: "Scores exacts",
  temps: "Temps de marquage",
  corners: "Corners",
  cartons: "Cartons",
  tirs: "Tirs",
  statistiques: "Statistiques",
  joueur: "Marchés joueurs",
  combine: "Combinés",
};

export const periodesMarche: Record<string, string> = {
  match: "Match",
  mi_temps: "Mi-temps",
  seconde_mi_temps: "2e mi-temps",
  prolongation: "Prolongation",
  tirs_au_but: "Tirs au but",
  set_1: "1er set",
  tie_break: "Jeu décisif",
  quart_1: "1er quart-temps",
  periode_1: "1re période",
  manche_1: "1re manche",
  carte_1: "Carte 1",
  "15_min": "15e minute",
  "30_min": "30e minute",
  "60_min": "60e minute",
  "75_min": "75e minute",
};

export const sujetsMarche: Record<string, string> = {
  match: "Match",
  team: "Équipe",
  player: "Joueur",
};

export const typesLigne: Record<string, string> = {
  aucune: "Sans ligne",
  simple: "Une ligne",
  double: "Deux lignes",
  intervalle: "Intervalle",
  libre: "Ligne libre",
};

export function libelleFamille(famille: string): string {
  return famillesMarches[famille] ?? famille;
}

export function libellePeriode(periode: string): string {
  return periodesMarche[periode] ?? periode;
}

export function libelleSujet(sujet: string): string {
  return sujetsMarche[sujet] ?? sujet;
}

/** Décrit la ligne et le sujet d'un marché en une phrase courte. */
export function descriptionMarche(marche: {
  line: number | null;
  line2: number | null;
  subject_team_name: string | null;
  subject_player: string | null;
}): string {
  const morceaux: string[] = [];
  if (marche.subject_team_name) morceaux.push(marche.subject_team_name);
  if (marche.subject_player) morceaux.push(marche.subject_player);
  if (marche.line !== null) {
    morceaux.push(`ligne ${marche.line}`);
  }
  if (marche.line2 !== null) {
    morceaux.push(`2e ligne ${marche.line2}`);
  }
  return morceaux.join(" · ");
}

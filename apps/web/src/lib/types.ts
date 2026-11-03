/** Types partagés avec l'API (voir apps/api/app/schemas). */

export interface Utilisateur {
  id: string;
  email: string;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface EtatAuth {
  admin_configured: boolean;
  authenticated: boolean;
  user: Utilisateur | null;
}

export interface Sport {
  id: string;
  code: string;
  name: string;
}

export interface Competition {
  id: string;
  sport_id: string;
  name: string;
  country: string | null;
  tier: number | null;
  is_active: boolean;
}

export interface Saison {
  id: string;
  competition_id: string;
  label: string;
  start_date: string | null;
  end_date: string | null;
  is_current: boolean;
}

export interface Equipe {
  id: string;
  sport_id: string;
  name: string;
  short_name: string | null;
  country: string | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export type StatutRencontre = "programme" | "en_cours" | "termine" | "reporte" | "annule";

export interface Rencontre {
  id: string;
  season_id: string;
  home_team_id: string;
  away_team_id: string;
  kickoff_at: string;
  status: StatutRencontre;
  home_score: number | null;
  away_score: number | null;
  half_time_home_score: number | null;
  half_time_away_score: number | null;
  venue: string | null;
  referee: string | null;
  notes: string | null;
  home_team_name: string;
  away_team_name: string;
  competition_name: string;
  season_label: string;
}

export interface EquipeRef {
  id: string;
  name: string;
  short_name: string | null;
}

export interface Statistique {
  id: string;
  match_id: string;
  team_id: string;
  is_home: boolean;
  goals_for: number | null;
  goals_against: number | null;
  shots: number | null;
  shots_on_target: number | null;
  possession: number | null;
  corners: number | null;
  yellow_cards: number | null;
  red_cards: number | null;
  expected_goals: number | null;
}

export interface RencontreDetail extends Rencontre {
  home_team: EquipeRef;
  away_team: EquipeRef;
  stats: Statistique[];
}

export interface ResumeTableauDeBord {
  competitions: number;
  teams: number;
  matches: number;
  matchs_a_venir: number;
  matchs_termines: number;
  prochaines_rencontres: Rencontre[];
  derniers_resultats: Rencontre[];
  avertissement: string;
}

export interface Preferences {
  cote_min: number;
  cote_max: number;
  nb_selections_defaut: number;
  marches_autorises: string[];
  demi_vie_jours: number;
  nb_matchs_historique: number;
}

export const statutsRencontre: Record<StatutRencontre, string> = {
  programme: "Programmé",
  en_cours: "En cours",
  termine: "Terminé",
  reporte: "Reporté",
  annule: "Annulé",
};

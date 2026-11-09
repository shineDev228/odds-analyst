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
  sport_id: string;
  sport_code: string;
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

export type SujetMarche = "match" | "team" | "player";

export type TypeLigne = "aucune" | "simple" | "double" | "intervalle" | "libre";

export interface ModeleMarche {
  code: string;
  sport_code: string | null;
  name: string;
  family: string;
  period: string;
  subject: SujetMarche;
  line_kind: TypeLigne;
  selection_templates: Array<{ code: string; label: string }>;
  description: string | null;
  is_active: boolean;
}

export interface Cote {
  id: string;
  selection_id: string;
  decimal_odds: number;
  captured_at: string;
  bookmaker: string;
  source: string;
  note: string | null;
}

export interface SelectionMarche {
  id: string;
  market_id: string;
  code: string;
  label: string;
  line: number | null;
  sort_order: number;
  latest_odds: number | null;
  latest_captured_at: string | null;
  implied_probability: number | null;
  fair_probability: number | null;
  fair_odds: number | null;
  odds_count: number;
  history: Cote[];
}

export interface Marche {
  id: string;
  match_id: string;
  template_code: string | null;
  name: string;
  family: string;
  period: string;
  subject: SujetMarche;
  subject_team_id: string | null;
  subject_team_name: string | null;
  subject_player: string | null;
  line: number | null;
  line2: number | null;
  is_custom: boolean;
  notes: string | null;
  created_at: string;
  latest_captured_at: string | null;
  overround_percent: number | null;
  implied_probability_total: number | null;
  is_complete: boolean;
  selections: SelectionMarche[];
}

export interface SelectionPrediction {
  code: string;
  label: string;
  probability: number;
  low: number;
  high: number;
}

export interface TotalPrediction {
  line: number;
  over: SelectionPrediction;
  under: SelectionPrediction;
}

export interface ScoreExactPrediction {
  label: string;
  home_goals: number;
  away_goals: number;
  probability: number;
}

export interface QualitePrediction {
  level: string;
  label: string;
  matches_home: number;
  matches_away: number;
  effective_home: number;
  effective_away: number;
  warnings: string[];
}

export interface Prediction {
  match_id: string;
  model_version: string;
  computed_at: string;
  expected_goals_home: number;
  expected_goals_away: number;
  expected_goals_total: number;
  quality: QualitePrediction;
  resultat: SelectionPrediction[];
  double_chance: SelectionPrediction[];
  totaux: TotalPrediction[];
  btts: SelectionPrediction[];
  scores_exacts: ScoreExactPrediction[];
  config: Record<string, number | string>;
  avertissement: string;
}

export interface SelectionCombinaison {
  match_id: string;
  market_id: string;
  selection_id: string;
  match_label: string;
  competition_name: string;
  kickoff_at: string;
  market_name: string;
  selection_label: string;
  decimal_odds: number;
  probability: number;
  low: number;
  high: number;
}

export interface Combinaison {
  selections: SelectionCombinaison[];
  total_odds: number;
  probability: number;
  low: number;
  high: number;
  expected_value: number;
}

export interface ParametresCombinaison {
  nombre_selections: number;
  cote_min: number;
  cote_max: number;
  marches_autorises: string[];
  limite: number;
}

export interface ReponseCombinaisons {
  combinaisons: Combinaison[];
  parametres: ParametresCombinaison;
  matchs_examines: number;
  matchs_disponibles: number;
  matchs_ignores: number;
  selections_disponibles: number;
  recherche_tronquee: boolean;
  message: string;
  avertissement: string;
}

export type StatutReglement =
  | "gagnee"
  | "perdue"
  | "remboursee"
  | "en_attente"
  | "indisponible";

export interface SelectionEnregistree {
  id: string;
  position: number;
  match_id: string | null;
  market_id: string | null;
  selection_id: string | null;
  match_label: string;
  competition_name: string;
  kickoff_at: string;
  market_name: string;
  market_family: string;
  market_period: string;
  selection_code: string;
  selection_label: string;
  line: number | null;
  decimal_odds: number;
  probability: number;
  low: number;
  high: number;
  status: StatutReglement;
  status_label: string;
  reason: string;
  home_score: number | null;
  away_score: number | null;
}

export interface CombinaisonEnregistree {
  id: string;
  created_at: string;
  nombre_selections: number;
  cote_min: number;
  cote_max: number;
  marches_autorises: string[];
  total_odds: number;
  probability: number;
  low: number;
  high: number;
  expected_value: number;
  note: string | null;
  status: StatutReglement;
  status_label: string;
  effective_odds: number;
  payout_units: number | null;
  net_units: number | null;
  selections: SelectionEnregistree[];
}

export interface ResumePerformance {
  total: number;
  en_attente: number;
  gagnees: number;
  perdues: number;
  remboursees: number;
  indisponibles: number;
  reglees: number;
  taux_reussite: number | null;
  cote_moyenne: number | null;
  unites_engagees: number;
  unites_retournees: number;
  resultat_net: number;
  roi: number | null;
  avertissement: string;
}

export const statutsRencontre: Record<StatutRencontre, string> = {
  programme: "Programmé",
  en_cours: "En cours",
  termine: "Terminé",
  reporte: "Reporté",
  annule: "Annulé",
};

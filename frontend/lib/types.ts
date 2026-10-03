export type Team = { program_id: number; name: string; gender: "men" | "women" };

export type Fixture = {
  source_match_id: number; season: string; gender: "men" | "women";
  match_date: string; match_time?: string | null; home_team: string; away_team: string;
  venue_name?: string | null; status: string;
  projection_available?: boolean;
};

export type Summary = {
  wins: number; losses: number; win_percentage: number; recent_form: string;
  average_margin: number; average_team_score: number;
};

export type Pairing = {
  position: number;
  team_one_player_id: number | null; team_one_player: string; team_one_rating: number | null;
  team_one_rating_date: string | null; team_one_is_forfeit: boolean; team_one_probability: number;
  team_two_player_id: number | null; team_two_player: string; team_two_rating: number | null;
  team_two_rating_date: string | null; team_two_is_forfeit: boolean;
};

export type Projection = {
  available: boolean; mode: string; mode_label?: string; reason?: string; note: string; pairings?: Pairing[];
  team_one_probability?: number; team_two_probability?: number;
  team_one_expected_wins?: number; team_two_expected_wins?: number;
  team_one_score_distribution?: number[];
  lineup_confidence?: number;
  data_timestamp?: string | null; model_version?: string; training_cutoff?: string;
};

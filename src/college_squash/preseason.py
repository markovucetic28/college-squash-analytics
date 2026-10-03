import json
from pathlib import Path

import pandas as pd

from college_squash.clublocker import normalize_team_name
from college_squash.current_season import CURRENT_DIVISIONS, CURRENT_SEASON
from college_squash.player_modeling import (
    expected_individual_wins, lineup_score_distribution, probability_at_least_five,
)
from college_squash.lineup_projection import lineup_confidence

TEAM_LINEUP_SIZE = 9
MINIMUM_PLAYABLE_ROSTER = 7


CURRENT_ROSTER_SCHEMA = """
CREATE TABLE IF NOT EXISTS current_roster_players (
    season TEXT NOT NULL,
    gender TEXT NOT NULL CHECK (gender IN ('men', 'women')),
    division_id INTEGER NOT NULL,
    team_id INTEGER NOT NULL,
    team_name TEXT NOT NULL,
    player_id INTEGER NOT NULL,
    display_name TEXT NOT NULL,
    current_rating REAL,
    rating_date TEXT NOT NULL,
    source_url TEXT NOT NULL,
    PRIMARY KEY (division_id, team_id, player_id)
);
CREATE INDEX IF NOT EXISTS current_roster_name_index
ON current_roster_players (display_name);
CREATE INDEX IF NOT EXISTS current_roster_team_index
ON current_roster_players (gender, team_name);
"""


def load_current_rosters(raw_directory):
    """Normalize official current rosters while retaining their source identity."""
    raw_directory = Path(raw_directory)
    metadata_path = raw_directory / f"current_{CURRENT_SEASON}" / "rosters.metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    rating_date = pd.Timestamp(metadata["retrieved_at_utc"]).strftime("%Y-%m-%d")
    rows = []
    for gender, division_id in CURRENT_DIVISIONS.items():
        for path in sorted((raw_directory / "player_rosters").glob(f"{division_id}_*.json")):
            team_id = int(path.stem.split("_", 1)[1])
            for player in json.loads(path.read_text(encoding="utf-8")):
                player_id = int(player.get("playerid") or 0)
                name = " ".join(str(player.get("player") or "").split())
                if player_id <= 0 or not name or name in {"N/A", ", N/A"}:
                    continue
                rating = pd.to_numeric(player.get("CurrentRating"), errors="coerce")
                rows.append({
                    "season": CURRENT_SEASON, "gender": gender,
                    "division_id": division_id, "team_id": team_id,
                    "team_name": normalize_team_name(player.get("teamname") or ""),
                    "player_id": player_id, "display_name": name,
                    "current_rating": None if pd.isna(rating) or rating <= 0 else float(rating),
                    "rating_date": rating_date,
                    "source_url": f"https://api.ussquash.com/resources/teams/{team_id}/players",
                })
    frame = pd.DataFrame(rows)
    if not frame.empty and frame[["division_id", "team_id", "player_id"]].duplicated().any():
        raise ValueError("Duplicate player in a current roster")
    return frame


def sync_current_rosters(connection, raw_directory):
    rosters = load_current_rosters(raw_directory)
    connection.executescript(CURRENT_ROSTER_SCHEMA)
    connection.execute("DELETE FROM current_roster_players WHERE season=?", (CURRENT_SEASON,))
    if not rosters.empty:
        connection.executemany(
            "INSERT INTO current_roster_players VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            list(rosters.itertuples(index=False, name=None)),
        )
    connection.commit()
    return len(rosters)


def current_team_names(connection, gender):
    return [row["team_name"] for row in connection.execute(
        """SELECT DISTINCT team_name FROM current_roster_players
           WHERE season=? AND gender=? ORDER BY team_name""", (CURRENT_SEASON, gender)
    )]


def current_roster(connection, team_name, gender):
    roster = pd.read_sql_query(
        """SELECT player_id, display_name, current_rating, rating_date, source_url
           FROM current_roster_players WHERE season=? AND gender=? AND team_name=?
           ORDER BY current_rating DESC, display_name""",
        connection, params=(CURRENT_SEASON, gender, team_name),
    )
    if roster.empty:
        return roster
    history = pd.read_sql_query(
        """
        SELECT player_id, AVG(position) prior_average_position,
               COUNT(*) prior_appearances,
               SUM(won) verified_wins, COUNT(*) verified_matches
        FROM (
            SELECT im.home_player_id player_id, im.position,
                   CASE WHEN im.winner_side='H' THEN 1 ELSE 0 END won
            FROM individual_matches im JOIN matches m USING(source_match_id)
            WHERE m.season='2025-26'
            UNION ALL
            SELECT im.away_player_id player_id, im.position,
                   CASE WHEN im.winner_side='V' THEN 1 ELSE 0 END won
            FROM individual_matches im JOIN matches m USING(source_match_id)
            WHERE m.season='2025-26'
        ) GROUP BY player_id
        """, connection,
    )
    career = pd.read_sql_query(
        """
        SELECT player_id, SUM(won) career_wins, COUNT(*) career_matches FROM (
            SELECT home_player_id player_id, CASE WHEN winner_side='H' THEN 1 ELSE 0 END won
            FROM individual_matches
            UNION ALL
            SELECT away_player_id player_id, CASE WHEN winner_side='V' THEN 1 ELSE 0 END won
            FROM individual_matches
        ) GROUP BY player_id
        """, connection,
    )
    roster = roster.merge(history, on="player_id", how="left").merge(career, on="player_id", how="left")
    for column in ["prior_appearances", "verified_wins", "verified_matches", "career_wins", "career_matches"]:
        roster[column] = roster[column].fillna(0).astype(int)
    return roster


def preseason_lineup(connection, team_name, gender):
    """Project the rated current roster, adding bottom-position forfeits when needed."""
    roster = current_roster(connection, team_name, gender)
    rated = roster[roster["current_rating"].notna()].copy()
    if len(rated) < MINIMUM_PLAYABLE_ROSTER:
        return None, 0.0
    lineup = rated.nlargest(TEAM_LINEUP_SIZE, "current_rating").sort_values(
        ["current_rating", "display_name"], ascending=[False, True]
    ).reset_index(drop=True)
    lineup.insert(0, "position", range(1, len(lineup) + 1))
    lineup["is_forfeit"] = False
    prior_coverage = float((lineup["prior_appearances"] > 0).mean())
    confidence = 0.6 + 0.4 * prior_coverage
    for position in range(len(lineup) + 1, TEAM_LINEUP_SIZE + 1):
        lineup.loc[len(lineup)] = {
            "position": position, "player_id": None, "display_name": "Forfeit",
            "current_rating": None, "rating_date": None, "source_url": None,
            "prior_average_position": None, "prior_appearances": 0,
            "verified_wins": 0, "verified_matches": 0, "career_wins": 0,
            "career_matches": 0, "is_forfeit": True,
        }
    return lineup, confidence


def current_season_lineup(connection, team_name, gender):
    """Return the latest complete lineup only after three prior current-season scorecards."""
    try:
        rows = connection.execute("""
            SELECT lm.source_match_id, lm.match_date, lim.position,
                   CASE WHEN lm.home_team=? THEN lim.home_player_id ELSE lim.away_player_id END player_id
            FROM live_matches lm JOIN live_individual_matches lim USING(source_match_id)
            WHERE lm.status='completed' AND lm.gender=? AND (lm.home_team=? OR lm.away_team=?)
            ORDER BY lm.match_date, lm.source_match_id, lim.position
        """, (team_name, gender, team_name, team_name)).fetchall()
    except Exception:
        return None, 0.0, 0
    histories = []
    for match_id in dict.fromkeys(row["source_match_id"] for row in rows):
        lineup = [row["player_id"] for row in rows if row["source_match_id"] == match_id]
        if len(lineup) == 9: histories.append(lineup)
    if len(histories) < 3: return None, 0.0, len(histories)
    projected = histories[-1]
    roster = pd.read_sql_query(
        """SELECT player_id, display_name, current_rating, rating_date,
                  0 prior_appearances
           FROM current_roster_players WHERE season=? AND gender=? AND team_name=?""",
        connection, params=(CURRENT_SEASON, gender, team_name),
    ).set_index("player_id")
    projected = [player_id for player_id in projected if player_id in roster.index]
    projected += [player_id for player_id in roster.sort_values("current_rating", ascending=False).index
                  if player_id not in projected][:TEAM_LINEUP_SIZE - len(projected)]
    if len(projected) < MINIMUM_PLAYABLE_ROSTER:
        return None, 0.0, len(histories)
    confidence = lineup_confidence(histories[-5:], projected)
    lineup = roster.loc[projected[:TEAM_LINEUP_SIZE]].reset_index()
    if lineup["current_rating"].isna().any(): return None, confidence, len(histories)
    lineup.insert(0, "position", range(1, len(lineup) + 1))
    lineup["is_forfeit"] = False
    for position in range(len(lineup) + 1, TEAM_LINEUP_SIZE + 1):
        lineup.loc[len(lineup)] = {
            "position": position, "player_id": None, "display_name": "Forfeit",
            "current_rating": None, "rating_date": None, "prior_appearances": 0,
            "is_forfeit": True,
        }
    return lineup, confidence, len(histories)


def custom_lineup(connection, team_name, gender, slots):
    """Build a temporary rated lineup from nine validated player/forfeit slots."""
    if len(slots) != TEAM_LINEUP_SIZE:
        raise ValueError("A custom lineup must contain exactly nine positions")
    player_ids = [player_id for player_id in slots if player_id is not None]
    if len(player_ids) != len(set(player_ids)):
        raise ValueError("A player cannot appear in more than one position")
    if not MINIMUM_PLAYABLE_ROSTER <= len(player_ids) <= TEAM_LINEUP_SIZE:
        raise ValueError("A custom lineup must contain at least seven eligible players")
    if slots[:len(player_ids)] != player_ids or any(
            player_id is not None for player_id in slots[len(player_ids):]):
        raise ValueError("Forfeits must occupy only the lowest lineup positions")

    roster = current_roster(connection, team_name, gender).set_index("player_id")
    invalid = [player_id for player_id in player_ids if player_id not in roster.index]
    if invalid:
        raise ValueError(f"Player {invalid[0]} is not on this team's current official roster")
    missing_rating = [player_id for player_id in player_ids
                      if pd.isna(roster.loc[player_id, "current_rating"])]
    if missing_rating:
        raise ValueError(f"Player {missing_rating[0]} does not have a valid current rating")

    rows = []
    for position, player_id in enumerate(slots, 1):
        if player_id is None:
            rows.append({
                "position": position, "player_id": None, "display_name": "Forfeit",
                "current_rating": None, "rating_date": None,
                "prior_appearances": 0, "is_forfeit": True,
            })
        else:
            player = roster.loc[player_id]
            rows.append({
                "position": position, "player_id": int(player_id),
                "display_name": player["display_name"],
                "current_rating": float(player["current_rating"]),
                "rating_date": player["rating_date"],
                "prior_appearances": int(player["prior_appearances"]),
                "is_forfeit": False,
            })
    return pd.DataFrame(rows)


def predict_lineups(artifact, first, second, first_confidence, second_confidence, mode):
    if first is None or second is None:
        return None
    feature_rows = []
    for position in range(1, 10):
        one = first.iloc[position - 1]
        two = second.iloc[position - 1]
        one_forfeit = bool(one.get("is_forfeit", False))
        two_forfeit = bool(two.get("is_forfeit", False))
        if one_forfeit or two_forfeit:
            # A single forfeit is a forced result, not a model-generated individual match.
            team_one_probability = 0.5 if one_forfeit and two_forfeit else float(two_forfeit)
        elif int(one["player_id"]) < int(two["player_id"]):
            difference = float(one["current_rating"] - two["current_rating"])
            team_one_is_a = True
        else:
            difference = float(two["current_rating"] - one["current_rating"])
            team_one_is_a = False
        if not one_forfeit and not two_forfeit:
            probability_a = artifact["model"].predict_proba(pd.DataFrame([{
                "official_rating_diff": difference, "position": position,
            }]))[0, 1]
            team_one_probability = float(probability_a if team_one_is_a else 1 - probability_a)
        feature_rows.append({
            "position": position,
            "team_one_player_id": None if one_forfeit else int(one["player_id"]),
            "team_one_player": one["display_name"],
            "team_one_rating": None if one_forfeit else float(one["current_rating"]),
            "team_one_rating_date": one["rating_date"],
            "team_one_prior_appearances": int(one["prior_appearances"]),
            "team_one_is_forfeit": one_forfeit,
            "team_one_probability": team_one_probability,
            "team_two_player_id": None if two_forfeit else int(two["player_id"]),
            "team_two_player": two["display_name"],
            "team_two_rating": None if two_forfeit else float(two["current_rating"]),
            "team_two_rating_date": two["rating_date"],
            "team_two_prior_appearances": int(two["prior_appearances"]),
            "team_two_is_forfeit": two_forfeit,
        })
    pairings = pd.DataFrame(feature_rows)
    probabilities = pairings["team_one_probability"].tolist()
    score_distribution = lineup_score_distribution(probabilities)
    return {
        "mode": mode,
        "pairings": pairings,
        "team_one_expected_wins": expected_individual_wins(probabilities),
        "team_two_expected_wins": 9 - expected_individual_wins(probabilities),
        "team_one_probability": probability_at_least_five(probabilities),
        "team_one_score_distribution": [float(value) for value in score_distribution],
        "lineup_confidence": min(first_confidence, second_confidence),
        "team_one_lineup_confidence": first_confidence,
        "team_two_lineup_confidence": second_confidence,
    }


def predict_preseason_matchup(connection, artifact, team_one, team_two, gender):
    """Score a roster-constrained preseason lineup with the unchanged rating model."""
    first, first_confidence = preseason_lineup(connection, team_one, gender)
    second, second_confidence = preseason_lineup(connection, team_two, gender)
    return predict_lineups(artifact, first, second, first_confidence, second_confidence,
                           "Preseason projection")


def predict_current_season_matchup(connection, artifact, team_one, team_two, gender):
    first, first_confidence, first_count = current_season_lineup(connection, team_one, gender)
    second, second_confidence, second_count = current_season_lineup(connection, team_two, gender)
    if min(first_count, second_count) < 3 or min(first_confidence, second_confidence) < .75:
        return None
    return predict_lineups(artifact, first, second, first_confidence, second_confidence,
                           "Current-season projected lineup")

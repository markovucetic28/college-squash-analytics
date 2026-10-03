import hashlib
import json
import sqlite3
from datetime import datetime, timezone


CURRENT_SEASON = "2026-27"
MINIMUM_PRIOR_LINEUPS = 3
MINIMUM_LINEUP_CONFIDENCE = 0.75
MODEL_VERSION = "official-rating-logistic-v1"
FEATURE_VERSION = "official-rating-difference-position-v1"
TRAINING_CUTOFF = "2025-26"


LIVE_SCHEMA = """
CREATE TABLE IF NOT EXISTS live_matches (
    source_match_id INTEGER PRIMARY KEY,
    season TEXT NOT NULL,
    gender TEXT NOT NULL CHECK (gender IN ('men', 'women')),
    division_id INTEGER NOT NULL,
    match_date TEXT NOT NULL,
    match_time TEXT,
    home_team_id INTEGER NOT NULL,
    home_team TEXT NOT NULL,
    away_team_id INTEGER NOT NULL,
    away_team TEXT NOT NULL,
    venue_name TEXT,
    status TEXT NOT NULL CHECK (status IN ('scheduled', 'completed', 'excluded')),
    home_score INTEGER,
    away_score INTEGER,
    source_url TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    retrieved_at_utc TEXT NOT NULL,
    warning TEXT
);

CREATE TABLE IF NOT EXISTS live_individual_matches (
    individual_match_id INTEGER PRIMARY KEY,
    source_match_id INTEGER NOT NULL REFERENCES live_matches(source_match_id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position BETWEEN 1 AND 9),
    home_player_id INTEGER NOT NULL,
    away_player_id INTEGER NOT NULL,
    winner_side TEXT NOT NULL CHECK (winner_side IN ('H', 'V')),
    winner_player_id INTEGER NOT NULL,
    loser_player_id INTEGER NOT NULL,
    game_scores_winner_first TEXT NOT NULL,
    source_url TEXT NOT NULL,
    UNIQUE (source_match_id, position)
);

CREATE TABLE IF NOT EXISTS live_player_ratings (
    player_id INTEGER NOT NULL,
    rating_date TEXT NOT NULL,
    rating REAL NOT NULL,
    retrieved_at_utc TEXT NOT NULL,
    source_url TEXT NOT NULL,
    PRIMARY KEY (player_id, rating_date)
);

CREATE TABLE IF NOT EXISTS refresh_runs (
    refresh_id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at_utc TEXT NOT NULL,
    completed_at_utc TEXT,
    status TEXT NOT NULL,
    summary_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prediction_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER NOT NULL,
    generated_at_utc TEXT NOT NULL,
    prediction_mode TEXT NOT NULL,
    team_one_probability REAL,
    expected_score REAL,
    lineup_confidence REAL,
    payload_json TEXT NOT NULL,
    model_version TEXT NOT NULL,
    training_cutoff TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    UNIQUE (fixture_id, generated_at_utc, prediction_mode)
);
"""


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def ensure_live_schema(connection):
    connection.executescript(LIVE_SCHEMA)


def stable_hash(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def prediction_mode(*, verified_lineup=False, current_lineups=0,
                    lineup_confidence=0.0, preseason_available=False,
                    team_model_available=False):
    """Choose a mode from evidence available at prediction time."""
    if verified_lineup:
        return {"mode": "verified", "reason": "Exact official pairings are available."}
    if (current_lineups >= MINIMUM_PRIOR_LINEUPS
            and lineup_confidence >= MINIMUM_LINEUP_CONFIDENCE):
        return {
            "mode": "projected",
            "reason": "Current-season lineup evidence passes the fixed readiness policy.",
        }
    if preseason_available:
        return {
            "mode": "preseason",
            "reason": "Current-season lineup evidence is not sufficient yet.",
        }
    if team_model_available:
        return {"mode": "team_only", "reason": "A complete rated lineup is unavailable."}
    return {"mode": "unavailable", "reason": "Neither player nor team inputs are sufficient."}


def upsert_live_match(connection, match):
    """Insert or transition one stable source match without creating duplicates."""
    values = (
        int(match["source_match_id"]), match.get("season", CURRENT_SEASON), match["gender"],
        int(match["division_id"]), match["match_date"], match.get("match_time"),
        int(match["home_team_id"]), match["home_team"], int(match["away_team_id"]),
        match["away_team"], match.get("venue_name"), match["status"],
        match.get("home_score"), match.get("away_score"), match["source_url"],
        match.get("source_hash") or stable_hash(match),
        match.get("retrieved_at_utc") or utc_now(), match.get("warning"),
    )
    connection.execute("""
        INSERT INTO live_matches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_match_id) DO UPDATE SET
          match_date=excluded.match_date, match_time=excluded.match_time,
          home_team_id=excluded.home_team_id, home_team=excluded.home_team,
          away_team_id=excluded.away_team_id, away_team=excluded.away_team,
          venue_name=excluded.venue_name, status=excluded.status,
          home_score=excluded.home_score, away_score=excluded.away_score,
          source_hash=excluded.source_hash, retrieved_at_utc=excluded.retrieved_at_utc,
          warning=excluded.warning
    """, values)


def store_complete_scorecard(connection, source_match_id, rows):
    if len(rows) != 9 or {int(row["position"]) for row in rows} != set(range(1, 10)):
        raise ValueError("A verified scorecard must contain positions 1-9 exactly once")
    home_wins = sum(row["winner_side"] == "H" for row in rows)
    match = connection.execute(
        "SELECT home_score, away_score FROM live_matches WHERE source_match_id=?",
        (int(source_match_id),),
    ).fetchone()
    if match is None or (home_wins, 9 - home_wins) != tuple(match):
        raise ValueError("Individual wins do not reproduce the team score")
    connection.executemany("""
        INSERT INTO live_individual_matches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(individual_match_id) DO NOTHING
    """, [(
        int(row["individual_match_id"]), int(source_match_id), int(row["position"]),
        int(row["home_player_id"]), int(row["away_player_id"]), row["winner_side"],
        int(row["winner_player_id"]), int(row["loser_player_id"]),
        row["game_scores_winner_first"], row["source_url"],
    ) for row in rows])


def insert_ratings(connection, ratings):
    connection.executemany("""
        INSERT INTO live_player_ratings VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(player_id, rating_date) DO NOTHING
    """, [(
        int(row["player_id"]), row["rating_date"], float(row["rating"]),
        row["retrieved_at_utc"], row["source_url"],
    ) for row in ratings])


def save_prediction_snapshot(connection, fixture_id, projection, generated_at_utc=None):
    generated = generated_at_utc or utc_now()
    payload = json.dumps(projection, sort_keys=True)
    connection.execute("""
        INSERT OR IGNORE INTO prediction_snapshots
        (fixture_id, generated_at_utc, prediction_mode, team_one_probability,
         expected_score, lineup_confidence, payload_json, model_version,
         training_cutoff, feature_version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        int(fixture_id), generated, projection["mode"],
        projection.get("team_one_probability"), projection.get("team_one_expected_wins"),
        projection.get("lineup_confidence"), payload, MODEL_VERSION,
        TRAINING_CUTOFF, FEATURE_VERSION,
    ))


def status_payload(connection):
    ensure_live_schema(connection)
    last = connection.execute(
        "SELECT completed_at_utc, summary_json FROM refresh_runs WHERE status='success' "
        "ORDER BY refresh_id DESC LIMIT 1"
    ).fetchone()
    counts = dict(connection.execute("""
        SELECT
          SUM(status='completed') completed_team_matches,
          SUM(status='scheduled') remaining_scheduled_fixtures,
          SUM(status='excluded') excluded_records
        FROM live_matches WHERE season=?
    """, (CURRENT_SEASON,)).fetchone())
    complete_scorecards = connection.execute(
        "SELECT COUNT(*) FROM (SELECT source_match_id FROM live_individual_matches "
        "GROUP BY source_match_id HAVING COUNT(*)=9)"
    ).fetchone()[0]
    summary = json.loads(last["summary_json"]) if last else {}
    try:
        short_rosters = [dict(row) for row in connection.execute("""
            SELECT gender, team_name, COUNT(*) roster_size,
                   COUNT(current_rating) rated_players,
                   MAX(0, 9 - COUNT(current_rating)) forfeited_positions
            FROM current_roster_players WHERE season=?
            GROUP BY gender, team_name HAVING COUNT(current_rating) < 9
            ORDER BY gender, team_name
        """, (CURRENT_SEASON,))]
    except sqlite3.OperationalError:
        short_rosters = []
    return {
        "current_season": CURRENT_SEASON,
        "last_successful_refresh": last["completed_at_utc"] if last else None,
        "last_schedule_refresh": summary.get("last_schedule_refresh"),
        "last_rating_refresh": summary.get("last_rating_refresh"),
        "completed_team_matches": counts.get("completed_team_matches") or 0,
        "remaining_scheduled_fixtures": counts.get("remaining_scheduled_fixtures") or 0,
        "complete_scorecards": complete_scorecards,
        "teams_with_lineup_evidence": summary.get("teams_with_lineup_evidence", 0),
        "teams_ready_for_projected_mode": summary.get("projected_ready_teams", 0),
        "short_roster_count": len(short_rosters),
        "short_rosters": short_rosters,
        "warnings": summary.get("warnings", []),
        "model": {
            "version": MODEL_VERSION, "training_cutoff": TRAINING_CUTOFF,
            "feature_version": FEATURE_VERSION, "frozen": True,
        },
    }


def prospective_metrics(rows):
    eligible = [row for row in rows if row.get("outcome") in (0, 1)
                and row.get("probability") is not None]
    if not eligible:
        return {"predictions": 0, "accuracy": None, "log_loss": None, "brier": None}
    import math
    probabilities = [min(1 - 1e-15, max(1e-15, float(row["probability"]))) for row in eligible]
    outcomes = [int(row["outcome"]) for row in eligible]
    return {
        "predictions": len(eligible),
        "accuracy": sum((p >= .5) == bool(y) for p, y in zip(probabilities, outcomes)) / len(eligible),
        "log_loss": -sum(y * math.log(p) + (1-y) * math.log(1-p)
                         for p, y in zip(probabilities, outcomes)) / len(eligible),
        "brier": sum((p-y) ** 2 for p, y in zip(probabilities, outcomes)) / len(eligible),
    }


def live_elos(connection, gender, initial=1500.0, k_factor=24.0):
    """Replay current results chronologically; all matches on one date use pre-day Elo."""
    rows = connection.execute("""
        SELECT * FROM live_matches WHERE season=? AND gender=? AND status='completed'
        ORDER BY match_date, source_match_id
    """, (CURRENT_SEASON, gender)).fetchall()
    ratings = {}
    for date in dict.fromkeys(row["match_date"] for row in rows):
        changes = {}
        for row in (item for item in rows if item["match_date"] == date):
            home = ratings.get(row["home_team"], initial); away = ratings.get(row["away_team"], initial)
            expected = 1 / (1 + 10 ** ((away-home)/400)); outcome = float(row["home_score"] > row["away_score"])
            change = k_factor * (outcome-expected)
            changes[row["home_team"]] = changes.get(row["home_team"], 0) + change
            changes[row["away_team"]] = changes.get(row["away_team"], 0) - change
        for team, change in changes.items(): ratings[team] = ratings.get(team, initial) + change
    return ratings


def live_rankings(connection, gender):
    rows = connection.execute("""
        SELECT * FROM live_matches WHERE season=? AND gender=? AND status='completed'
        ORDER BY match_date, source_match_id
    """, (CURRENT_SEASON, gender)).fetchall()
    teams = sorted({row["home_team"] for row in rows} | {row["away_team"] for row in rows})
    records = {}
    for team in teams:
        games = []
        for row in rows:
            if team not in (row["home_team"], row["away_team"]): continue
            home = team == row["home_team"]
            score = row["home_score"] if home else row["away_score"]
            opponent_score = row["away_score"] if home else row["home_score"]
            games.append((row["match_date"], score > opponent_score, score-opponent_score,
                          row["away_team"] if home else row["home_team"]))
        wins = sum(game[1] for game in games); total = len(games)
        records[team] = {"team": team, "wins": wins, "losses": total-wins,
                         "win_percentage": wins/total if total else 0,
                         "average_margin": sum(game[2] for game in games)/total if total else 0,
                         "recent_form": "".join("W" if game[1] else "L" for game in games[-5:]),
                         "opponents": [game[3] for game in games]}
    elos = live_elos(connection, gender)
    for team, record in records.items():
        opponent_rates = [records[name]["win_percentage"] for name in record.pop("opponents") if name in records]
        record["strength_of_schedule"] = sum(opponent_rates)/len(opponent_rates) if opponent_rates else 0
        record["elo"] = elos.get(team, 1500.0)
        program = connection.execute("SELECT program_id FROM programs WHERE canonical_name=? AND gender=?", (team, gender)).fetchone()
        record["program_id"] = program[0] if program else None
    ordered = sorted(records.values(), key=lambda row: (-row["win_percentage"], -row["strength_of_schedule"], -row["average_margin"], row["team"]))
    for rank, row in enumerate(ordered, 1): row["rank"] = rank
    return ordered


def live_team_summary(connection, team_name, gender):
    return next((row for row in live_rankings(connection, gender) if row["team"] == team_name), None)

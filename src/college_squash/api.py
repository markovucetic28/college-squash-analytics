from functools import lru_cache
import json
import math
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import joblib
import pandas as pd
from pydantic import BaseModel

from college_squash.analytics import (
    available_seasons, division_rankings, head_to_head_history, player_profile,
    player_search, program_elos, scheduled_matches, season_by_season_summary,
    season_history, strength_of_schedule, team_summary,
)
from college_squash.database import connect_database as open_database
from college_squash.modeling import predict_matchup
from college_squash.live_season import (
    FEATURE_VERSION, MODEL_VERSION, TRAINING_CUTOFF, ensure_live_schema,
    live_rankings, live_team_summary, prediction_mode, status_payload,
)
from college_squash.preseason import (
    CURRENT_SEASON, current_roster, predict_current_season_matchup,
    predict_preseason_matchup, preseason_lineup, custom_lineup, predict_lineups,
)
from college_squash.recent_form import recent_form_by_player


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = Path(os.environ.get(
    "DATABASE_PATH", os.environ.get("COLLEGE_SQUASH_DB", PROJECT_ROOT / "data/college_squash.db")
))
PLAYER_MODEL_PATH = Path(os.environ.get(
    "COLLEGE_SQUASH_PLAYER_MODEL", PROJECT_ROOT / "data/preseason_player_model.joblib"
))
TEAM_MODEL_PATH = Path(os.environ.get(
    "COLLEGE_SQUASH_TEAM_MODEL", PROJECT_ROOT / "data/matchup_model.joblib"
))
LATEST_COMPLETE_SEASON = "2025-26"
DEPLOYMENT_ENV = os.environ.get("DEPLOYMENT_ENV", "development").lower()


def connect_database(database_path=DATABASE_PATH):
    read_only = os.environ.get("DATABASE_READ_ONLY", "0").lower() in {"1", "true", "yes"}
    return open_database(database_path, read_only=read_only)

app = FastAPI(
    title="College Squash Analytics API", version="1.0.0",
    docs_url=None if DEPLOYMENT_ENV == "production" else "/docs",
    redoc_url=None if DEPLOYMENT_ENV == "production" else "/redoc",
)
def cors_origins():
    configured = os.environ.get("CORS_ORIGINS", "")
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return ["http://localhost:3000", "http://127.0.0.1:3000"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def player_model():
    return joblib.load(PLAYER_MODEL_PATH)


@lru_cache(maxsize=1)
def team_model():
    return joblib.load(TEAM_MODEL_PATH)


def clean_value(value):
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def records(frame):
    return [{key: clean_value(value) for key, value in row.items()}
            for row in frame.to_dict("records")]


def display_player_name(name):
    if "," not in name:
        return name
    last_name, first_names = (part.strip() for part in name.split(",", 1))
    return " ".join(part for part in (first_names, last_name) if part)


def format_game_score(raw_score):
    """Turn the stored winner-first game array into a compact human-readable score."""
    if not raw_score:
        return None
    try:
        games = json.loads(raw_score) if isinstance(raw_score, str) else raw_score
        return ", ".join(f"{int(first)}–{int(second)}" for first, second in games)
    except (TypeError, ValueError, json.JSONDecodeError):
        return str(raw_score)


def program_row(connection, program_id):
    row = connection.execute(
        "SELECT program_id, canonical_name, gender FROM programs WHERE program_id=?",
        (int(program_id),),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Team not found")
    return row


def team_context(connection, team_name, gender):
    try:
        summary = team_summary(connection, team_name, gender, LATEST_COMPLETE_SEASON)
        history = team_summary(connection, team_name, gender)
        sos = strength_of_schedule(connection, team_name, gender, LATEST_COMPLETE_SEASON)
    except ValueError:
        summary = history = None
        sos = None
    elo = program_elos(connection, gender, LATEST_COMPLETE_SEASON).get(team_name, 1500.0)
    current = live_team_summary(connection, team_name, gender)
    return {
        "previous_season": summary,
        "current_season": current,
        "historical_record": history,
        "strength_of_schedule": sos,
        "elo": elo,
    }


def projection_payload(connection, team_one, team_two, gender):
    result = predict_current_season_matchup(connection, player_model(), team_one, team_two, gender)
    live_mode = result is not None
    if result is None:
        result = predict_preseason_matchup(connection, player_model(), team_one, team_two, gender)
    if result is None:
        try:
            probability = predict_matchup(
                connection, team_model(), team_one, team_two, gender
            )
        except ValueError:
            probability = None
        decision = prediction_mode(team_model_available=probability is not None)
        return {
            "mode": decision["mode"], "mode_label": "Team-only estimate",
            "reason": decision["reason"], "available": False,
            "team_one_probability": probability,
            "team_two_probability": None if probability is None else 1 - probability,
            "data_timestamp": current_data_timestamp(),
            "model_version": MODEL_VERSION, "training_cutoff": TRAINING_CUTOFF,
            "feature_version": FEATURE_VERSION,
            "note": ("A playable rated lineup is unavailable. The team-level "
                     "estimate is shown when both programs have verified history."),
        }
    probability = float(result["team_one_probability"])
    result["pairings"] = add_pairing_recent_form(connection, result["pairings"])
    decision = prediction_mode(current_lineups=3, lineup_confidence=float(result["lineup_confidence"])) if live_mode else prediction_mode(preseason_available=True)
    return {
        "mode": decision["mode"], "mode_label": result["mode"],
        "reason": decision["reason"],
        "available": True,
        "note": (("Projected from earlier complete 2026–27 scorecards and current ratings. "
                  if live_mode else "Projected from the current 2026–27 roster, current ratings, and prior varsity lineup history. ")
                 + "Actual lineup may differ."),
        "team_one_probability": probability,
        "team_two_probability": 1 - probability,
        "team_one_expected_wins": float(result["team_one_expected_wins"]),
        "team_two_expected_wins": float(result["team_two_expected_wins"]),
        "lineup_confidence": float(result["lineup_confidence"]),
        "team_one_lineup_confidence": float(result["team_one_lineup_confidence"]),
        "team_two_lineup_confidence": float(result["team_two_lineup_confidence"]),
        "pairings": records(result["pairings"]),
        "team_one_score_distribution": result["team_one_score_distribution"],
        "data_timestamp": current_data_timestamp(),
        "rating_timestamps": sorted(
            {date for date in result["pairings"]["team_one_rating_date"] if date}
            | {date for date in result["pairings"]["team_two_rating_date"] if date}
        ),
        "model_version": MODEL_VERSION, "training_cutoff": TRAINING_CUTOFF,
        "feature_version": FEATURE_VERSION,
    }


def current_data_timestamp():
    path = PROJECT_ROOT / "data/processed/current_season_readiness.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8")).get("retrieved_at_utc")


@lru_cache(maxsize=4)
def current_recent_form_cache(data_timestamp):
    """Refresh the descriptive roster-form cache when the live data timestamp changes."""
    with connect_database(DATABASE_PATH) as connection:
        ids = [row[0] for row in connection.execute(
            "SELECT DISTINCT player_id FROM current_roster_players WHERE season=?",
            (CURRENT_SEASON,),
        )]
        return recent_form_by_player(connection, player_model(), ids)


def recent_forms(connection, player_ids):
    requested = {int(player_id) for player_id in player_ids if pd.notna(player_id)}
    cache = current_recent_form_cache(current_data_timestamp())
    missing = requested - cache.keys()
    return {**{player_id: cache[player_id] for player_id in requested if player_id in cache},
            **recent_form_by_player(connection, player_model(), missing)}


def add_pairing_recent_form(connection, pairings):
    """Attach descriptive form in one batch; prediction inputs remain unchanged."""
    player_ids = list(pairings["team_one_player_id"]) + list(pairings["team_two_player_id"])
    form = recent_forms(connection, player_ids)
    pairings = pairings.copy()
    pairings["team_one_recent_form"] = pairings["team_one_player_id"].map(form)
    pairings["team_two_recent_form"] = pairings["team_two_player_id"].map(form)
    return pairings


class CustomLineupRequest(BaseModel):
    team_one_id: int
    team_two_id: int
    team_one_lineup: list[int | None]
    team_two_lineup: list[int | None]


@app.post("/api/compare/custom-lineup")
def custom_lineup_projection(request: CustomLineupRequest):
    if request.team_one_id == request.team_two_id:
        raise HTTPException(400, "Choose two different teams")
    with connect_database(DATABASE_PATH) as connection:
        first = program_row(connection, request.team_one_id)
        second = program_row(connection, request.team_two_id)
        if first["gender"] != second["gender"]:
            raise HTTPException(400, "Teams must be in the same division")
        try:
            first_lineup = custom_lineup(
                connection, first["canonical_name"], first["gender"], request.team_one_lineup
            )
            second_lineup = custom_lineup(
                connection, second["canonical_name"], second["gender"], request.team_two_lineup
            )
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        result = predict_lineups(
            player_model(), first_lineup, second_lineup, 1.0, 1.0,
            "Custom lineup scenario",
        )
        result["pairings"] = add_pairing_recent_form(connection, result["pairings"])
    probability = float(result["team_one_probability"])
    return {
        "mode": "custom", "mode_label": "Custom scenario", "available": True,
        "reason": "User-edited, session-only lineup.",
        "note": "This lineup was edited by you and is not an official or projected lineup.",
        "team_one_probability": probability,
        "team_two_probability": 1 - probability,
        "team_one_expected_wins": float(result["team_one_expected_wins"]),
        "team_two_expected_wins": float(result["team_two_expected_wins"]),
        "lineup_confidence": None,
        "pairings": records(result["pairings"]),
        "team_one_score_distribution": result["team_one_score_distribution"],
        "data_timestamp": current_data_timestamp(),
        "model_version": MODEL_VERSION, "training_cutoff": TRAINING_CUTOFF,
        "feature_version": FEATURE_VERSION,
    }


@app.get("/api/health")
def health():
    return {"status": "ok", "season": CURRENT_SEASON}


@app.get("/api/status")
def data_status():
    with connect_database(DATABASE_PATH) as connection:
        return status_payload(connection)


@app.get("/api/schedule")
def schedule(
    gender: str | None = None,
    team: str | None = None,
    start: str | None = None,
    end: str | None = None,
    status: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    if gender not in (None, "men", "women"):
        raise HTTPException(400, "gender must be men or women")
    with connect_database(DATABASE_PATH) as connection:
        frame = scheduled_matches(connection, gender, team, start, end)
        roster_counts = {
            (row["gender"], row["team_name"]): row["rated_players"]
            for row in connection.execute("""
                SELECT gender, team_name, COUNT(current_rating) rated_players
                FROM current_roster_players WHERE season=?
                GROUP BY gender, team_name
            """, (CURRENT_SEASON,))
        }
    if not frame.empty:
        frame["projection_available"] = frame.apply(
            lambda match: (
                roster_counts.get((match["gender"], match["home_team"]), 0) >= 7
                and roster_counts.get((match["gender"], match["away_team"]), 0) >= 7
            ), axis=1,
        )
    if status and status.lower() != "all":
        frame = frame.loc[frame["status"].str.lower() == status.lower()]
    total = len(frame)
    return {"total": total, "offset": offset, "limit": limit,
            "items": records(frame.iloc[offset:offset + limit])}


@app.get("/api/matches/{match_id}")
def match_detail(match_id: int):
    with connect_database(DATABASE_PATH) as connection:
        ensure_live_schema(connection)
        fixture = connection.execute(
            "SELECT * FROM live_matches WHERE source_match_id=?", (match_id,)
        ).fetchone() or connection.execute(
            "SELECT * FROM scheduled_matches WHERE source_match_id=?", (match_id,)
        ).fetchone()
        if fixture is None:
            raise HTTPException(404, "Scheduled match not found")
        fixture = dict(fixture)
        away, home, gender = fixture["away_team"], fixture["home_team"], fixture["gender"]
        program_ids = {
            row["canonical_name"]: row["program_id"]
            for row in connection.execute(
                "SELECT program_id, canonical_name FROM programs WHERE gender=?",
                (gender,),
            )
        }
        projection = projection_payload(connection, away, home, gender)
        try:
            meetings = records(head_to_head_history(connection, away, home, gender))
        except ValueError:
            meetings = []
        return {
            **fixture,
            "team_one": away,
            "team_two": home,
            "team_one_id": program_ids.get(away),
            "team_two_id": program_ids.get(home),
            "team_one_context": team_context(connection, away, gender),
            "team_two_context": team_context(connection, home, gender),
            "projection": projection,
            "historical_meetings": meetings,
        }


@app.get("/api/teams")
def teams(gender: str | None = None):
    params = [CURRENT_SEASON]
    where = "WHERE cr.season=?"
    if gender:
        if gender not in ("men", "women"):
            raise HTTPException(400, "gender must be men or women")
        where += " AND cr.gender=?"
        params.append(gender)
    with connect_database(DATABASE_PATH) as connection:
        rows = connection.execute(f"""
            SELECT DISTINCT p.program_id, cr.team_name name, cr.gender
            FROM current_roster_players cr
            LEFT JOIN programs p ON p.canonical_name=cr.team_name AND p.gender=cr.gender
            {where} ORDER BY cr.team_name, cr.gender
        """, params).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/teams/{team_id}")
def team_detail(team_id: int):
    with connect_database(DATABASE_PATH) as connection:
        team = program_row(connection, team_id)
        name, gender = team["canonical_name"], team["gender"]
        roster = current_roster(connection, name, gender)
        lineup, confidence = preseason_lineup(connection, name, gender)
        positions = {} if lineup is None else dict(zip(lineup["player_id"], lineup["position"]))
        if not roster.empty:
            roster["projected_position"] = roster["player_id"].map(positions)
            roster["verified_losses"] = roster["career_matches"] - roster["career_wins"]
            form = recent_forms(connection, roster["player_id"])
            roster["recent_form"] = roster["player_id"].map(form)
        fixtures = scheduled_matches(connection, gender, name)
        history = season_history(connection, name, gender, LATEST_COMPLETE_SEASON)
        seasons = season_by_season_summary(connection, name, gender)
        return {
            "program_id": team_id, "name": name, "gender": gender,
            "season": CURRENT_SEASON, "lineup_confidence": confidence,
            **team_context(connection, name, gender),
            "roster": records(roster),
            "schedule": records(fixtures),
            "previous_results": records(history.sort_values("date", ascending=False)),
            "season_history": records(seasons),
        }


@app.get("/api/players/search")
def search_players(q: str = "", limit: int = Query(20, ge=1, le=100)):
    if not q.strip():
        return []
    with connect_database(DATABASE_PATH) as connection:
        frame = player_search(connection, q, limit)
    items = records(frame)
    for item in items:
        item["name"] = display_player_name(item["display_name"])
    return items


@app.get("/api/search")
def global_search(q: str = "", limit: int = Query(8, ge=1, le=30)):
    if len(q.strip()) < 2:
        return {"teams": [], "players": []}
    with connect_database(DATABASE_PATH) as connection:
        player_items = search_players(q, limit)
        words = [word.lower() for word in q.split()]
        team_rows = connection.execute("""
            SELECT DISTINCT p.program_id, cr.team_name name, cr.gender
            FROM current_roster_players cr JOIN programs p
              ON p.canonical_name=cr.team_name AND p.gender=cr.gender
            WHERE cr.season=? ORDER BY cr.team_name, cr.gender
        """, (CURRENT_SEASON,)).fetchall()
    team_items = [dict(row) for row in team_rows
                  if all(word in row["name"].lower() for word in words)][:limit]
    return {"teams": team_items, "players": player_items}


@app.get("/api/players/{player_id}")
def player_detail(player_id: int):
    with connect_database(DATABASE_PATH) as connection:
        try:
            player, memberships, matches, ratings = player_profile(connection, player_id)
        except ValueError as error:
            raise HTTPException(404, str(error)) from error
        current = connection.execute("""
            SELECT cr.*, p.program_id FROM current_roster_players cr
            LEFT JOIN programs p ON p.canonical_name=cr.team_name AND p.gender=cr.gender
            WHERE cr.player_id=? LIMIT 1
        """, (player_id,)).fetchone()
        projected_position = None
        if current:
            lineup, _ = preseason_lineup(
                connection, current["team_name"], current["gender"]
            )
            if lineup is not None:
                position = lineup.loc[lineup["player_id"] == player_id, "position"]
                projected_position = None if position.empty else int(position.iloc[0])
        latest_rating = None
        if current and current["current_rating"]:
            latest_rating = {"rating": current["current_rating"],
                             "date": current["rating_date"]}
        elif not ratings.empty:
            latest = ratings.iloc[-1]
            latest_rating = {"rating": float(latest["rating"]),
                             "date": latest["date"].strftime("%Y-%m-%d")}
        wins = int((matches["result"] == "W").sum()) if not matches.empty else 0
        recent_form = recent_forms(connection, [player_id])[player_id]
        match_records = records(matches.head(50))
        for match in match_records:
            match["opponent"] = display_player_name(match["opponent"])
            match["formatted_score"] = format_game_score(match.pop("score", None))
        membership_records = records(memberships)
        return {
            **player, "name": display_player_name(player["display_name"]),
            "current_membership": dict(current) if current else None,
            "latest_membership": (
                dict(current) if current else
                membership_records[0] if membership_records else None
            ),
            "projected_position": projected_position,
            "recent_form": recent_form,
            "latest_rating": latest_rating,
            "verified_record": {"wins": wins, "losses": len(matches) - wins,
                                "matches": len(matches)},
            "average_position": None if matches.empty else float(matches["position"].mean()),
            "memberships": membership_records,
            "matches": match_records,
            "ratings": records(ratings),
        }


@app.get("/api/rankings")
def rankings(gender: str = "men", season: str = LATEST_COMPLETE_SEASON):
    if gender not in ("men", "women"):
        raise HTTPException(400, "gender must be men or women")
    with connect_database(DATABASE_PATH) as connection:
        if season == CURRENT_SEASON:
            return {"gender": gender, "season": season,
                    "items": live_rankings(connection, gender)}
        if season not in available_seasons(connection, gender):
            raise HTTPException(404, "Season not found")
        frame = division_rankings(connection, gender, season)
        elos = program_elos(connection, gender, season)
        frame["elo"] = frame["team"].map(elos)
        program_ids = {row["canonical_name"]: row["program_id"] for row in connection.execute(
            "SELECT program_id, canonical_name FROM programs WHERE gender=?", (gender,)
        )}
        frame["program_id"] = frame["team"].map(program_ids)
    return {"gender": gender, "season": season, "items": records(frame)}


@app.get("/api/compare")
def compare(team_one_id: int, team_two_id: int):
    if team_one_id == team_two_id:
        raise HTTPException(400, "Choose two different teams")
    with connect_database(DATABASE_PATH) as connection:
        first = program_row(connection, team_one_id)
        second = program_row(connection, team_two_id)
        if first["gender"] != second["gender"]:
            raise HTTPException(400, "Teams must be in the same division")
        gender = first["gender"]
        meetings = head_to_head_history(
            connection, first["canonical_name"], second["canonical_name"], gender
        )
        return {
            "team_one": {"program_id": team_one_id, "name": first["canonical_name"],
                         **team_context(connection, first["canonical_name"], gender)},
            "team_two": {"program_id": team_two_id, "name": second["canonical_name"],
                         **team_context(connection, second["canonical_name"], gender)},
            "gender": gender,
            "projection": projection_payload(
                connection, first["canonical_name"], second["canonical_name"], gender
            ),
            "historical_meetings": records(meetings),
        }


@app.get("/api/methodology/summary")
def methodology_summary():
    return {
        "coverage": "Six completed seasons: 2019–20 and 2021–22 through 2025–26.",
        "sources": "Public CSA / Club Locker schedules, scorecards, rosters, and ratings.",
        "rating_rule": "Historical ratings must satisfy rating_date < match_date.",
        "modes": ["Verified lineup", "Projected lineup", "Preseason projection",
                  "Team-only fallback"],
        "mode_definitions": {
            "Verified lineup": "Actual official lineup is known.",
            "Projected lineup": "Lineup inferred from recent official lineup evidence.",
            "Preseason projection": "Current roster ratings and prior lineup evidence are used.",
            "Team-only fallback": "Player-level lineup prediction is unavailable, so the team model is used.",
        },
        "production_model": "The validated production model is frozen. Research candidates are evaluated separately and are not live.",
        "recent_form": (
            "Recent form is descriptive only. It averages performance versus pre-match "
            "official-rating expectations over up to five rated matches, requires at least "
            "three, and does not change prediction probabilities."
        ),
        "freshness": "Schedule, scorecard, roster, and rating refresh status is available from the status service.",
        "external_results": {
            "team_model_accuracy": 0.784,
            "verified_lineup_accuracy": 0.896,
            "projected_lineup_accuracy": 0.856,
            "season": "2025-26",
        },
        "limitations": [
            "Historical feed coverage is not complete for every postseason.",
            "Preseason and projected lineups are uncertain until official scorecards exist.",
            "Project probabilities are estimates, not official CSA forecasts or guarantees.",
        ],
    }

import hashlib
import json
import sqlite3

import pytest

from college_squash.live_season import (
    ensure_live_schema, insert_ratings, prediction_mode, prospective_metrics,
    save_prediction_snapshot, status_payload, store_complete_scorecard, upsert_live_match,
)
from college_squash.preseason import CURRENT_ROSTER_SCHEMA, current_season_lineup


def connection():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    ensure_live_schema(db)
    return db


def match(status="scheduled", home_score=None, away_score=None):
    return {"source_match_id": 10, "season": "2026-27", "gender": "men",
            "division_id": 6376, "match_date": "2026-11-01", "home_team_id": 1,
            "home_team": "A", "away_team_id": 2, "away_team": "B",
            "status": status, "home_score": home_score, "away_score": away_score,
            "source_url": "https://example.test/10", "retrieved_at_utc": "2026-10-03T00:00:00Z"}


def scorecard():
    rows = []
    for position in range(1, 10):
        home_won = position <= 5
        rows.append({"individual_match_id": 100 + position, "position": position,
                     "home_player_id": 1000 + position, "away_player_id": 2000 + position,
                     "winner_side": "H" if home_won else "V",
                     "winner_player_id": (1000 if home_won else 2000) + position,
                     "loser_player_id": (2000 if home_won else 1000) + position,
                     "game_scores_winner_first": "[[11, 5], [11, 7], [11, 8]]",
                     "source_url": "https://example.test/scorecard"})
    return rows


def test_idempotent_scheduled_to_completed_transition_and_duplicate_prevention():
    db = connection(); upsert_live_match(db, match()); upsert_live_match(db, match())
    assert db.execute("SELECT COUNT(*) FROM live_matches").fetchone()[0] == 1
    upsert_live_match(db, match("completed", 5, 4)); store_complete_scorecard(db, 10, scorecard())
    store_complete_scorecard(db, 10, scorecard())
    assert db.execute("SELECT status FROM live_matches").fetchone()[0] == "completed"
    assert db.execute("SELECT COUNT(*) FROM live_individual_matches").fetchone()[0] == 9


def test_incomplete_scorecard_is_rejected_without_partial_rows():
    db = connection(); upsert_live_match(db, match("completed", 5, 4))
    with pytest.raises(ValueError): store_complete_scorecard(db, 10, scorecard()[:-1])
    assert db.execute("SELECT COUNT(*) FROM live_individual_matches").fetchone()[0] == 0


def test_rating_snapshots_are_append_only():
    db = connection(); rows = [{"player_id": 1, "rating_date": "2026-10-01", "rating": 6.1,
        "retrieved_at_utc": "2026-10-03T00:00:00Z", "source_url": "https://example.test/rating"}]
    insert_ratings(db, rows); insert_ratings(db, rows)
    newer = [{**rows[0], "rating_date": "2026-10-02", "rating": 6.2}]; insert_ratings(db, newer)
    assert db.execute("SELECT COUNT(*) FROM live_player_ratings").fetchone()[0] == 2


def test_prediction_modes_use_fixed_transition_policy():
    assert prediction_mode(preseason_available=True)["mode"] == "preseason"
    assert prediction_mode(current_lineups=3, lineup_confidence=.75)["mode"] == "projected"
    assert prediction_mode(verified_lineup=True)["mode"] == "verified"
    assert prediction_mode(team_model_available=True)["mode"] == "team_only"
    assert prediction_mode()["mode"] == "unavailable"


def test_prediction_snapshots_are_append_only_and_versioned():
    db = connection(); projection = {"mode": "preseason", "team_one_probability": .6,
        "team_one_expected_wins": 5.2, "lineup_confidence": .8, "pairings": []}
    save_prediction_snapshot(db, 10, projection, "2026-10-03T01:00:00Z")
    save_prediction_snapshot(db, 10, projection, "2026-10-03T02:00:00Z")
    assert db.execute("SELECT COUNT(*) FROM prediction_snapshots").fetchone()[0] == 2
    assert db.execute("SELECT frozen FROM (SELECT 1 frozen)").fetchone()[0] == 1


def test_status_and_prospective_metrics():
    db = connection(); upsert_live_match(db, match())
    db.execute("INSERT INTO refresh_runs(started_at_utc,completed_at_utc,status,summary_json) VALUES (?,?,?,?)",
               ("x", "y", "success", json.dumps({"projected_ready_teams": 2, "warnings": []})))
    status = status_payload(db)
    assert status["remaining_scheduled_fixtures"] == 1
    assert status["model"]["frozen"] is True
    metrics = prospective_metrics([{"probability": .8, "outcome": 1}, {"probability": .3, "outcome": 0}])
    assert metrics["predictions"] == 2 and metrics["accuracy"] == 1


def test_three_complete_current_lineups_create_projected_evidence():
    db = connection(); db.executescript(CURRENT_ROSTER_SCHEMA)
    db.executemany("INSERT INTO current_roster_players VALUES (?,?,?,?,?,?,?,?,?,?)", [
        ("2026-27", "men", 6376, 1, "A", player, f"Player {player}",
         7-player/100, "2026-10-01", "https://example.test/roster")
        for player in range(1, 10)
    ])
    for match_id in (10, 11, 12):
        item = match("completed", 5, 4); item["source_match_id"] = match_id
        item["match_date"] = f"2026-11-{match_id:02d}"; upsert_live_match(db, item)
        rows = scorecard()
        for row in rows:
            row["individual_match_id"] += match_id * 100
            row["home_player_id"] = row["position"]
            row["winner_player_id"] = row["position"] if row["winner_side"] == "H" else row["away_player_id"]
            row["loser_player_id"] = row["away_player_id"] if row["winner_side"] == "H" else row["position"]
        store_complete_scorecard(db, match_id, rows)
    lineup, confidence, count = current_season_lineup(db, "A", "men")
    assert count == 3 and len(lineup) == 9 and confidence >= .75

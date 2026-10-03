from pathlib import Path
import sqlite3
import sys

import pytest
import joblib


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from college_squash.analytics import (
    head_to_head, head_to_head_history, program_elos, scheduled_matches,
    season_history, team_summary,
)
from college_squash.clublocker import load_all_divisions
from college_squash.database import build_database, connect_database
from college_squash.preseason import preseason_lineup, predict_preseason_matchup


@pytest.fixture(scope="module")
def database(tmp_path_factory):
    database_path = tmp_path_factory.mktemp("database") / "college_squash.db"
    build_database(PROJECT_ROOT / "data/raw", database_path)
    return database_path


def test_database_loads_validated_dataset_with_foreign_keys(database):
    with connect_database(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 12
        assert connection.execute("SELECT COUNT(*) FROM divisions").fetchone()[0] == 12
        assert connection.execute("SELECT COUNT(*) FROM matches").fetchone()[0] == 3537
        assert connection.execute("SELECT COUNT(*) FROM scheduled_matches").fetchone()[0] == 426
        assert connection.execute("SELECT COUNT(*) FROM current_roster_players").fetchone()[0] == 837
        assert connection.execute(
            "SELECT COUNT(*) FROM teams WHERE is_varsity = 1"
        ).fetchone()[0] == 395
        assert connection.execute("SELECT COUNT(*) FROM programs").fetchone()[0] > 65
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_player_schema_preserves_scorecard_provenance(database):
    connection = connect_database(database)
    tables = {
        row["name"] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {"players", "player_team_seasons", "individual_matches"} <= tables
    row = connection.execute(
        "SELECT position, source_url FROM individual_matches LIMIT 1"
    ).fetchone()
    if row is not None:
        assert 1 <= row["position"] <= 9
        assert "/scorecards/" in row["source_url"]


def test_rebuild_replaces_database_reproducibly(database):
    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM matches WHERE source_match_id = 204965")
        connection.commit()

    counts = build_database(PROJECT_ROOT / "data/raw", database)

    assert counts["matches"] == 3537
    assert counts["scheduled_matches"] == 426
    with connect_database(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM matches").fetchone()[0] == 3537


@pytest.mark.parametrize(
    ("team", "gender", "wins", "losses"),
    [
        ("Harvard University", "men", 10, 7),
        ("University of Pennsylvania", "men", 20, 0),
        ("Trinity College", "women", 18, 1),
    ],
)
def test_team_summaries_match_standardized_dataset(database, team, gender, wins, losses):
    matches, _, _ = load_all_divisions(PROJECT_ROOT / "data/raw")
    direct_matches = matches.loc[
        (matches["division"] == gender)
        & (matches["season"] == "2024-25")
        & ((matches["home_team"] == team) | (matches["away_team"] == team))
    ]
    expected_scores = direct_matches.apply(
        lambda row: row["home_score"] if row["home_team"] == team else row["away_score"],
        axis=1,
    )
    expected_opponent_scores = direct_matches.apply(
        lambda row: row["away_score"] if row["home_team"] == team else row["home_score"],
        axis=1,
    )

    with connect_database(database) as connection:
        summary = team_summary(connection, team, gender, "2024-25")

    assert summary["wins"] == wins
    assert summary["losses"] == losses
    assert summary["average_team_score"] == pytest.approx(expected_scores.mean())
    assert summary["average_margin"] == pytest.approx(
        (expected_scores - expected_opponent_scores).mean()
    )


def test_history_and_head_to_head(database):
    with connect_database(database) as connection:
        history = season_history(connection, "Harvard University", "men", "2024-25")
        summary = team_summary(connection, "Harvard University", "men", "2024-25")
        record = head_to_head(
            connection, "Harvard University", "Yale University", "men", "2024-25"
        )

    assert len(history) == 17
    assert history["date"].is_monotonic_increasing
    assert history.iloc[-1]["opponent"] == "Columbia University"
    assert summary["recent_form"] == "WWLWL"
    assert summary["average_team_score"] == pytest.approx(5.470588)
    assert summary["average_opponent_score"] == pytest.approx(3.529412)
    assert record == {
        "team_one": "Harvard University",
        "team_two": "Yale University",
        "matches": 2,
        "team_one_wins": 0,
        "team_two_wins": 2,
    }


def test_product_analytics_keep_schedule_separate_and_trace_historical_meetings(database):
    with connect_database(database) as connection:
        schedule = scheduled_matches(connection, "men", "Harvard University")
        meetings = head_to_head_history(
            connection, "Harvard University", "Yale University", "men"
        )
        elos = program_elos(connection, "men", "2025-26")

    assert not schedule.empty
    assert set(schedule["status"]) == {"Scheduled"}
    assert schedule["source_match_id"].is_unique
    assert meetings["date"].is_monotonic_decreasing
    assert set(meetings["result"]) <= {"W", "L"}
    assert elos["Trinity College"] > elos["Harvard University"]


def test_preseason_projection_uses_only_current_roster_players(database):
    artifact = joblib.load(PROJECT_ROOT / "data/preseason_player_model.joblib")
    with connect_database(database) as connection:
        lineup, confidence = preseason_lineup(connection, "Harvard University", "men")
        roster_ids = {
            row["player_id"] for row in connection.execute(
                """SELECT player_id FROM current_roster_players
                   WHERE team_name='Harvard University' AND gender='men'"""
            )
        }
        prediction = predict_preseason_matchup(
            connection, artifact, "Harvard University", "Yale University", "men"
        )

    assert len(lineup) == 9
    assert set(lineup["player_id"]) <= roster_ids
    assert lineup["current_rating"].is_monotonic_decreasing
    assert 0 <= confidence <= 1
    assert len(prediction["pairings"]) == 9
    assert prediction["pairings"]["team_one_probability"].between(0, 1).all()
    assert 0 <= prediction["team_one_probability"] <= 1


def test_unknown_team_is_rejected(database):
    with connect_database(database) as connection:
        with pytest.raises(ValueError, match="Unknown men's varsity team"):
            team_summary(connection, "Imaginary University", "men")


def test_program_identity_links_historical_name_variants(database):
    with connect_database(database) as connection:
        rows = connection.execute(
            """SELECT d.season, t.source_name, p.canonical_name
               FROM teams t JOIN divisions d USING (division_id)
               JOIN programs p USING (program_id)
               WHERE p.canonical_name='Bowdoin College' AND p.gender='men'
                 AND t.is_varsity=1 ORDER BY d.season"""
        ).fetchall()
    assert len(rows) == 6
    assert rows[0]["source_name"] == "Bowdoin College Men"
    assert {row["canonical_name"] for row in rows} == {"Bowdoin College"}

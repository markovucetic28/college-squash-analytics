from pathlib import Path
import sqlite3
import sys

import joblib
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from college_squash.database import connect_database
from college_squash.preseason import preseason_lineup, predict_preseason_matchup


@pytest.mark.parametrize(("keep", "forfeits", "available"), [
    (9, 0, True), (8, 1, True), (7, 2, True), (6, 0, False),
])
def test_minimum_roster_rule(keep, forfeits, available):
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE current_roster_players (
          season TEXT, gender TEXT, division_id INTEGER, team_id INTEGER,
          team_name TEXT, player_id INTEGER, display_name TEXT,
          current_rating REAL, rating_date TEXT, source_url TEXT
        );
        CREATE TABLE matches (source_match_id INTEGER, season TEXT);
        CREATE TABLE individual_matches (
          source_match_id INTEGER, home_player_id INTEGER, away_player_id INTEGER,
          position INTEGER, winner_side TEXT
        );
    """)
    connection.executemany(
        "INSERT INTO current_roster_players VALUES ('2026-27','men',1,1,'Test College',?,?,?,'2026-10-03','source')",
        [(player_id, f"Player {player_id}", 10-player_id/10) for player_id in range(1, keep+1)],
    )
    lineup, _ = preseason_lineup(connection, "Test College", "men")
    connection.close()
    assert (lineup is not None) is available
    if available:
        assert len(lineup) == 9
        assert int(lineup["is_forfeit"].sum()) == forfeits
        assert lineup.loc[lineup["is_forfeit"], "player_id"].isna().all()


def test_dickinson_women_short_roster_projection():
    artifact = joblib.load(PROJECT_ROOT / "data/preseason_player_model.joblib")
    with connect_database(PROJECT_ROOT / "data/college_squash.db") as connection:
        lineup, _ = preseason_lineup(connection, "Dickinson College", "women")
        prediction = predict_preseason_matchup(
            connection, artifact, "Dickinson College", "Dartmouth College", "women"
        )
    assert len(lineup.loc[~lineup["is_forfeit"]]) == 8
    assert lineup.iloc[-1]["display_name"] == "Forfeit"
    assert prediction["pairings"].iloc[-1]["team_one_probability"] == 0
    assert prediction["pairings"].iloc[-1]["team_one_is_forfeit"]
    assert prediction["team_one_expected_wins"] == pytest.approx(
        prediction["pairings"]["team_one_probability"].sum()
    )


def test_short_roster_orientation_is_complementary():
    artifact = joblib.load(PROJECT_ROOT / "data/preseason_player_model.joblib")
    with connect_database(PROJECT_ROOT / "data/college_squash.db") as connection:
        first = predict_preseason_matchup(connection, artifact, "Dickinson College", "Dartmouth College", "women")
        reverse = predict_preseason_matchup(connection, artifact, "Dartmouth College", "Dickinson College", "women")
    assert first["team_one_probability"] + reverse["team_one_probability"] == pytest.approx(1)
    assert all(
        left + right == pytest.approx(1)
        for left, right in zip(first["pairings"]["team_one_probability"], reverse["pairings"]["team_one_probability"])
    )

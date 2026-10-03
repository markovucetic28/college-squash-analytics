from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app import player_search_label
from college_squash.analytics import player_search
from college_squash.database import connect_database


DATABASE_PATH = PROJECT_ROOT / "data" / "college_squash.db"


def test_search_returns_canonical_team_context_for_partial_current_names():
    with connect_database(DATABASE_PATH) as connection:
        raven = player_search(connection, "Rav", 30)
        azzam = player_search(connection, "Azz", 30)

    assert "canonical_team_name" in raven.columns
    assert (
        (raven["display_name"] == "Raven, Charlie")
        & (raven["canonical_team_name"] == "Hamilton College")
        & (raven["season"] == "2026-27")
    ).any()
    assert {"Azzam, Kareem", "Azzam, Omar"}.issubset(set(azzam["display_name"]))


def test_search_includes_historical_players_and_ambiguous_name_context():
    with connect_database(DATABASE_PATH) as connection:
        historical = player_search(connection, "Franklyn", 30)
        smiths = player_search(connection, "Smith", 30)

    franklyn = historical.loc[historical["display_name"] == "Smith, Franklyn"].iloc[0]
    assert franklyn["season"] == "2025-26"
    assert franklyn["is_current"] == 0

    labels = [player_search_label(row) for row in smiths.to_dict("records")]
    assert len(labels) > 1
    assert all(" — " in label and ", Men (" in label or ", Women (" in label for label in labels)


def test_player_search_label_handles_missing_optional_context():
    label = player_search_label({"player_id": 1, "display_name": "Smith, Charlotte"})

    assert label == (
        "Charlotte Smith — Team unavailable, Division Unavailable "
        "(Season unavailable)"
    )


def test_normalized_search_finds_reordered_partial_name():
    with connect_database(DATABASE_PATH) as connection:
        results = player_search(connection, "char raven", 30)

    assert "Raven, Charlie" in set(results["display_name"])


def test_every_current_roster_player_is_discoverable_by_normalized_name():
    with connect_database(DATABASE_PATH) as connection:
        roster = connection.execute(
            "SELECT player_id, display_name FROM current_roster_players ORDER BY player_id"
        ).fetchall()
        assert len(roster) == 837
        for player in roster:
            name = player["display_name"]
            if "," in name:
                last_name, first_names = name.split(",", 1)
                search_text = f"{first_names.strip()} {last_name.strip()}"
            else:
                search_text = name
            results = player_search(connection, search_text, 30)
            assert int(player["player_id"]) in set(results["player_id"]), name


def test_empty_query_returns_no_candidates():
    with connect_database(DATABASE_PATH) as connection:
        results = player_search(connection, "   ")

    assert results.empty

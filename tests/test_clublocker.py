import json
from pathlib import Path
import sys

import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from college_squash.clublocker import (
    calculate_team_record,
    load_all_divisions,
    load_division,
    normalize_team_name,
)


RAW_DIRECTORY = PROJECT_ROOT / "data/raw"


def test_all_official_divisions_build_one_unique_dataset():
    matches, exclusions, teams = load_all_divisions(RAW_DIRECTORY)

    assert len(matches) == 3537
    assert len(exclusions) == 704
    assert len(teams) == 395
    assert teams.groupby(["season", "division"]).size().to_dict() == {
        ("2019-20", "men"): 35, ("2019-20", "women"): 32,
        ("2021-22", "men"): 34, ("2021-22", "women"): 32,
        ("2022-23", "men"): 34, ("2022-23", "women"): 32,
        ("2023-24", "men"): 34, ("2023-24", "women"): 32,
        ("2024-25", "men"): 34, ("2024-25", "women"): 31,
        ("2025-26", "men"): 34, ("2025-26", "women"): 31,
    }
    assert matches["source_id"].is_unique
    assert not matches.duplicated(
        ["date", "division_id", "home_team_id", "away_team_id", "match_time"]
    ).any()
    assert set(matches["division"]) == {"men", "women"}
    assert matches["source_url"].str.startswith("https://clublocker.com/").all()


@pytest.mark.parametrize(
    ("team", "division", "wins", "losses"),
    [
        ("Harvard University", "men", 10, 7),
        ("University of Pennsylvania", "men", 20, 0),
        ("Trinity College", "women", 18, 1),
    ],
)
def test_sample_records_match_official_athletics_sources(team, division, wins, losses):
    matches, _, _ = load_all_divisions(RAW_DIRECTORY)
    record = calculate_team_record(matches, team, division, "2024-25")

    assert record["wins"] == wins
    assert record["losses"] == losses
    assert record["total_matches"] == wins + losses


def test_team_name_normalization_is_small_and_explicit():
    assert normalize_team_name(" Virginia,  University of ") == "University of Virginia"
    assert normalize_team_name("Trinity College") == "Trinity College"
    assert normalize_team_name("Bowdoin College Women") == "Bowdoin College"


def test_scheduled_and_tied_entries_are_logged(tmp_path):
    schedule = [
        {
            "scorecardid": 1,
            "matchdate": "01/01/25",
            "wTeamName": "Harvard University",
            "oTeamName": "Yale University",
            "hteamid": 10,
            "vteamid": 11,
            "Home_Matches_Won": 0,
            "Visitor_Matches_Won": 0,
            "Score_Entered": "Scheduled",
        },
        {
            "scorecardid": 2,
            "matchdate": "01/02/25",
            "wTeamName": "Harvard University",
            "oTeamName": "Yale University",
            "hteamid": 10,
            "vteamid": 11,
            "Home_Matches_Won": 4,
            "Visitor_Matches_Won": 4,
            "Score_Entered": "Confirmed",
        },
        {
            "scorecardid": 3,
            "matchdate": "01/03/25",
            "wTeamName": "Harvard University",
            "oTeamName": "Yale University",
            "hteamid": 10,
            "vteamid": 11,
            "Home_Matches_Won": 5,
            "Visitor_Matches_Won": 4,
            "Score_Entered": "Confirmed",
            "VenueName": "Harvard University",
        },
    ]
    teams = [{"team_id": 10, "team_name": "Harvard University"}]
    schedule_path = tmp_path / "schedule.json"
    teams_path = tmp_path / "teams.json"
    schedule_path.write_text(json.dumps(schedule), encoding="utf-8")
    teams_path.write_text(json.dumps(teams), encoding="utf-8")

    matches, exclusions, _ = load_division(
        schedule_path, teams_path, "men", 5208, "2024-25"
    )

    assert matches["source_id"].tolist() == [3]
    assert exclusions["reason"].tolist() == [
        "match is not confirmed",
        "confirmed entry has no match winner",
    ]


def test_record_requires_known_team():
    empty_matches = pd.DataFrame(
        columns=["division", "home_team", "away_team", "winner"]
    )
    with pytest.raises(ValueError, match="No men's matches"):
        calculate_team_record(empty_matches, "Unknown College", "men")

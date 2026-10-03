import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from college_squash.current_season import load_current_schedule


def test_current_schedule_is_separate_validated_and_traceable():
    schedule, exclusions = load_current_schedule(PROJECT_ROOT / "data/raw")

    assert len(schedule) == 426
    assert schedule.groupby("gender").size().to_dict() == {"men": 234, "women": 192}
    assert set(schedule["season"]) == {"2026-27"}
    assert set(schedule["status"]) == {"Scheduled"}
    assert schedule["source_match_id"].is_unique
    assert schedule["source_url"].str.startswith("https://clublocker.com/").all()
    assert len(exclusions) == 2
    assert set(exclusions["reason"]) == {
        "neither team is in the official varsity division standings"
    }


def test_confirmed_and_malformed_rows_are_not_loaded_as_scheduled(tmp_path):
    folder = tmp_path / "current_2026-27"
    folder.mkdir()
    rows = [
        {"scorecardid": 1, "matchdate": "11/01/26", "wTeamName": "A",
         "oTeamName": "B", "hteamid": 10, "vteamid": 11, "Score_Entered": "Confirmed"},
        {"scorecardid": 2, "matchdate": "bad", "wTeamName": "A",
         "oTeamName": "B", "hteamid": 10, "vteamid": 11, "Score_Entered": "Scheduled"},
    ]
    (folder / "csa_men_varsity_2026-27.json").write_text(json.dumps(rows))
    (folder / "csa_men_varsity_2026-27_teams.json").write_text(json.dumps([
        {"teamid": 10}, {"teamid": 11}
    ]))

    schedule, exclusions = load_current_schedule(tmp_path)

    assert schedule.empty
    assert len(exclusions) == 1
    assert exclusions.iloc[0]["reason"] == "scheduled match date is malformed"

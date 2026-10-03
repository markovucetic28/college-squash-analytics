from pathlib import Path
import sys

import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from college_squash.records import calculate_record, load_schedule, parse_schedule


RAW_PATH = PROJECT_ROOT / "data/raw/harvard_men_2024_25.html"


def test_official_schedule_produces_verified_record():
    matches, exclusions = load_schedule(RAW_PATH)
    record = calculate_record(matches)

    assert record == {
        "team": "Harvard Men",
        "wins": 10,
        "losses": 7,
        "total_matches": 17,
        "win_percentage": pytest.approx(10 / 17),
    }
    assert len(exclusions) == 1
    assert exclusions.iloc[0]["opponent_or_event"] == "CSA Individual National Championships"


def test_match_dates_and_source_ids_are_unique():
    matches, _ = load_schedule(RAW_PATH)

    assert matches["source_id"].is_unique
    assert not matches.duplicated(["date", "team", "opponent"]).any()
    assert matches["date"].is_monotonic_increasing


def test_result_must_agree_with_score():
    invalid_html = """
    <li class="sidearm-schedule-game" data-game-id="1">
      <div class="sidearm-schedule-game-opponent-name"><a>Yale</a></div>
      <div class="sidearm-schedule-game-conference-vs">vs</div>
      <div class="sidearm-schedule-game-result">W, 4-5</div>
      <button class="sidearm-schedule-game-toggle">Details - January 1, 2025</button>
    </li>
    """

    with pytest.raises(ValueError, match="disagree"):
        parse_schedule(invalid_html)


def test_record_rejects_unknown_results():
    matches = pd.DataFrame({"team": ["Harvard Men"], "result": ["T"]})

    with pytest.raises(ValueError, match="win or loss"):
        calculate_record(matches)


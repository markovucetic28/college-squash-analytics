from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from college_squash.analytics import (
    division_rankings,
    performance_trend,
    season_by_season_summary,
    strength_of_schedule,
)
from college_squash.clublocker import load_all_divisions
from college_squash.database import build_database, connect_database


@pytest.fixture(scope="module")
def database(tmp_path_factory):
    path = tmp_path_factory.mktemp("rankings") / "college_squash.db"
    build_database(PROJECT_ROOT / "data/raw", path)
    return path


def test_strength_of_schedule_matches_direct_pandas_calculation(database):
    matches, _, _ = load_all_divisions(PROJECT_ROOT / "data/raw")
    men = matches.loc[(matches["division"] == "men") & (matches["season"] == "2024-25")]
    team = "Harvard University"
    harvard_matches = men.loc[(men["home_team"] == team) | (men["away_team"] == team)]

    opponent_percentages = []
    for match in harvard_matches.itertuples():
        opponent = match.away_team if match.home_team == team else match.home_team
        opponent_matches = men.loc[
            (men["home_team"] == opponent) | (men["away_team"] == opponent)
        ]
        opponent_wins = (
            ((opponent_matches["home_team"] == opponent)
             & (opponent_matches["home_score"] > opponent_matches["away_score"]))
            | ((opponent_matches["away_team"] == opponent)
               & (opponent_matches["away_score"] > opponent_matches["home_score"]))
        ).sum()
        opponent_percentages.append(opponent_wins / len(opponent_matches))

    with connect_database(database) as connection:
        actual = strength_of_schedule(connection, team, "men", "2024-25")

    assert actual == pytest.approx(sum(opponent_percentages) / len(opponent_percentages))


def test_rankings_use_documented_sort_order(database):
    with connect_database(database) as connection:
        rankings = division_rankings(connection, "men", "2024-25")

    expected = rankings.sort_values(
        ["win_percentage", "strength_of_schedule", "average_margin", "team"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)
    assert rankings["team"].tolist() == expected["team"].tolist()
    assert rankings.iloc[0]["team"] == "University of Pennsylvania"
    assert rankings["rank"].tolist() == list(range(1, 35))


def test_performance_trend_for_harvard(database):
    with connect_database(database) as connection:
        trend = performance_trend(connection, "Harvard University", "men", "2024-25")

    assert len(trend) == 17
    assert trend.iloc[-1]["cumulative_wins"] == 10
    assert trend.iloc[-1]["cumulative_win_percentage"] == pytest.approx(10 / 17)
    assert trend.iloc[-1]["rolling_average_margin"] == pytest.approx(3.4)


def test_harvard_has_six_season_history(database):
    with connect_database(database) as connection:
        history = season_by_season_summary(connection, "Harvard University", "men")
    assert history["season"].tolist() == [
        "2019-20", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26"
    ]
    assert history.iloc[-1]["wins"] == 10
    assert history.iloc[-1]["losses"] == 5

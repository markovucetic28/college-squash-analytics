from pathlib import Path
import shutil
import sys

import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from college_squash.database import build_database, connect_database
from college_squash.modeling import (
    FEATURE_COLUMNS,
    build_feature_dataset,
    decayed_program_strength,
    elo_changes,
    elo_probability,
    recency_weights,
    regress_elo,
    walk_forward_evaluation,
)


@pytest.fixture(scope="module")
def model_database(tmp_path_factory):
    path = tmp_path_factory.mktemp("model") / "college_squash.db"
    build_database(PROJECT_ROOT / "data/raw", path)
    return path


@pytest.fixture(scope="module")
def features(model_database):
    with connect_database(model_database) as connection:
        return build_feature_dataset(connection)


def test_feature_dataset_has_one_row_per_verified_match(features):
    assert len(features) == 3537
    assert features["source_match_id"].is_unique
    assert not features[FEATURE_COLUMNS].isna().any().any()
    assert set(features["team_a_win"]) == {0, 1}


def test_each_season_starts_with_neutral_current_season_statistics(features):
    first_by_season = features.sort_values(["date", "source_match_id"]).groupby("season").head(1)
    assert (first_by_season["team_a_prior_matches"] == 0).all()
    assert (first_by_season["team_b_prior_matches"] == 0).all()
    assert (first_by_season["team_a_current_win_percentage"] == 0.5).all()
    assert (first_by_season["team_b_current_win_percentage"] == 0.5).all()


def test_prior_season_strength_is_neutral_only_in_first_season(features):
    first_season = features.loc[features["season"] == "2019-20"]
    assert (first_season["prior_season_strength_diff"] == 0).all()
    later = features.loc[features["season"] == "2021-22"]
    assert (later["prior_season_strength_diff"].abs() > 0).any()


def test_same_day_matches_do_not_leak_into_each_other(features):
    penn = features.loc[
        (features["date"] == "2024-11-16")
        & (features["gender"] == "men")
        & ((features["team_a"] == "University of Pennsylvania")
           | (features["team_b"] == "University of Pennsylvania"))
    ]
    assert len(penn) == 2
    prior_matches, win_percentages, elo_ratings = [], [], []
    for match in penn.itertuples():
        prefix = "team_a" if match.team_a == "University of Pennsylvania" else "team_b"
        prior_matches.append(getattr(match, f"{prefix}_prior_matches"))
        win_percentages.append(getattr(match, f"{prefix}_current_win_percentage"))
        elo_ratings.append(getattr(match, f"{prefix}_elo"))
    assert prior_matches == [1, 1]
    assert win_percentages[0] == pytest.approx(win_percentages[1])
    assert elo_ratings[0] == pytest.approx(elo_ratings[1])


def test_future_season_rows_cannot_change_earlier_features(model_database, tmp_path):
    truncated_path = tmp_path / "truncated.db"
    shutil.copy(model_database, truncated_path)
    with connect_database(truncated_path) as connection:
        connection.execute("DELETE FROM matches WHERE season = '2025-26'")
        connection.commit()
        truncated = build_feature_dataset(connection)
    with connect_database(model_database) as connection:
        full = build_feature_dataset(connection)
    earlier = full.loc[full["season"] != "2025-26"].reset_index(drop=True)
    pd.testing.assert_frame_equal(
        earlier[["source_match_id", *FEATURE_COLUMNS]],
        truncated[["source_match_id", *FEATURE_COLUMNS]].reset_index(drop=True),
    )


def test_recency_weighting_favors_recent_seasons(features):
    train = features.loc[features["season"].isin(["2019-20", "2021-22"])]
    weights = recency_weights(train, "2022-23")
    assert set(weights[train["season"] == "2019-20"]) == {0.75}
    assert set(weights[train["season"] == "2021-22"]) == {1.0}
    assert decayed_program_strength([0.8, 0.4]) == pytest.approx((0.8 * 0.6 + 0.4) / 1.6)


def test_elo_update_and_between_season_regression():
    assert elo_probability(1500, 1500) == pytest.approx(0.5)
    winner_change, loser_change = elo_changes(1500, 1500, 1)
    assert winner_change == pytest.approx(10)
    assert loser_change == pytest.approx(-10)
    assert regress_elo(1600) == pytest.approx(1575)


def test_walk_forward_uses_only_prior_seasons(features):
    evaluation = walk_forward_evaluation(features)
    assert [fold["test_season"] for fold in evaluation["folds"]] == [
        "2021-22", "2022-23", "2023-24", "2024-25", "2025-26"
    ]
    assert [fold["training_matches"] for fold in evaluation["folds"]] == [
        645, 1228, 1779, 2317, 2916
    ]
    assert [fold["test_matches"] for fold in evaluation["folds"]] == [
        583, 551, 538, 599, 621
    ]
    for fold in evaluation["folds"]:
        for name in ["baseline", "elo", "model"]:
            result = fold[f"{name}_metrics"]
            assert 0 <= result["accuracy"] <= 1
            assert result["log_loss"] > 0
            assert 0 <= result["brier_score"] <= 1


def test_model_earns_app_integration_against_both_baselines(features):
    aggregate = walk_forward_evaluation(features)["aggregate"]
    for baseline in ["baseline", "elo"]:
        assert aggregate["model"]["accuracy"] >= aggregate[baseline]["accuracy"]
        assert aggregate["model"]["log_loss"] <= aggregate[baseline]["log_loss"]
        assert aggregate["model"]["brier_score"] <= aggregate[baseline]["brier_score"]

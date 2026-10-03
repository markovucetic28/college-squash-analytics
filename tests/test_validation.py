from pathlib import Path
import sys

import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from college_squash.validation import (
    add_validation_groups,
    calibration_metrics,
    class_balance,
    confidence_analysis,
    performance_by,
)


@pytest.fixture()
def sample_matches():
    frame = pd.DataFrame({
        "season": ["2021-22", "2021-22", "2022-23", "2022-23"],
        "gender": ["men", "women", "men", "women"],
        "actual": [0, 1, 1, 0],
        "baseline_probability": [0.4, 0.6, 0.6, 0.4],
        "elo_probability": [0.3, 0.7, 0.7, 0.3],
        "model_probability": [0.2, 0.8, 0.8, 0.2],
        "team_a_elo": [1480, 1520, 1750, 1500],
        "team_b_elo": [1500, 1500, 1500, 1500],
        "elo_diff": [-20, 20, 250, 0],
        "prior_head_to_head_matches": [0, 1, 2, 0],
    })
    return add_validation_groups(frame)


def test_validation_buckets_use_only_pre_match_columns(sample_matches):
    assert sample_matches["closeness"].astype(str).tolist() == [
        "Very close (<50)", "Very close (<50)", "Heavy favorite (200+)",
        "Very close (<50)",
    ]
    assert sample_matches["prior_meeting"].tolist() == [False, True, True, False]
    assert sample_matches["dominant_team_involved"].tolist() == [False, False, True, False]


def test_class_balance_counts_each_target_class(sample_matches):
    balance = class_balance(sample_matches)
    assert balance["matches"].tolist() == [2, 2]
    assert balance["team_a_wins"].tolist() == [1, 1]
    assert balance["team_a_win_rate"].tolist() == [0.5, 0.5]


def test_group_performance_preserves_all_rows(sample_matches):
    results = performance_by(sample_matches, "gender")
    model = results.loc[results["model"] == "model"]
    assert model["matches"].sum() == len(sample_matches)
    assert (model["accuracy"] == 1).all()


def test_confidence_and_calibration_calculations(sample_matches):
    confidence = confidence_analysis(sample_matches)
    assert confidence["matches"].sum() == 4
    assert confidence.iloc[0]["mean_confidence"] == pytest.approx(0.8)
    assert confidence.iloc[0]["favorite_win_rate"] == pytest.approx(1.0)
    calibration = calibration_metrics(sample_matches)
    aggregate = calibration.loc[calibration["season"] == "aggregate"].iloc[0]
    assert aggregate["expected_calibration_error"] == pytest.approx(0.2)

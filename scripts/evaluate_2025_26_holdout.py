from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from college_squash.database import connect_database
from college_squash.modeling import build_feature_dataset, metrics, walk_forward_evaluation
from college_squash.player_modeling import (
    build_player_feature_dataset, official_rating_walk_forward,
)


TEST_SEASON = "2025-26"


def result(frame, probability_column):
    available = frame[frame[probability_column].notna()]
    if available.empty:
        return {"matches": 0, "accuracy": None, "log_loss": None, "brier_score": None}
    return {
        "matches": len(available),
        **metrics(available["actual_home_won"], available[probability_column]),
    }


def model_results(frame):
    groups = {
        "overall": frame,
        "first_time": frame[frame["prior_head_to_head_matches"] == 0],
        "repeat": frame[frame["prior_head_to_head_matches"] > 0],
        "close": frame[frame["elo_diff"].abs() < 100],
    }
    output = {}
    for label, group in groups.items():
        output[label] = {
            "team_model": result(group, "team_probability"),
            "verified_lineup": result(group, "official_rating_lineup_probability"),
            "projected_lineup": result(group, "projected_probability"),
        }
    return output


def main():
    connection = connect_database(PROJECT_ROOT / "data/college_squash.db")
    team_features = build_feature_dataset(connection)
    team_evaluation = walk_forward_evaluation(team_features)
    team_fold = next(
        fold for fold in team_evaluation["folds"] if fold["test_season"] == TEST_SEASON
    )
    player_features = build_player_feature_dataset(connection)
    rating_evaluation = official_rating_walk_forward(player_features)
    rating_fold = next(
        fold for fold in rating_evaluation["folds"] if fold["test_season"] == TEST_SEASON
    )
    team_predictions = team_evaluation["predictions"]
    team_predictions = team_predictions[team_predictions["season"] == TEST_SEASON].copy()
    team_predictions["source_match_id"] = team_features.loc[
        team_predictions.index, "source_match_id"
    ]
    team_predictions["prior_head_to_head_matches"] = team_features.loc[
        team_predictions.index, "prior_head_to_head_matches"
    ]
    team_predictions["elo_diff"] = team_features.loc[team_predictions.index, "elo_diff"]
    match_orientation = pd.read_sql_query(
        """
        SELECT m.source_match_id, home.name home_team, away.name away_team,
               CASE WHEN m.home_score > m.away_score THEN 1 ELSE 0 END actual_home_won
        FROM matches m
        JOIN teams home ON home.division_id=m.division_id AND home.team_id=m.home_team_id
        JOIN teams away ON away.division_id=m.division_id AND away.team_id=m.away_team_id
        WHERE m.season='2025-26'
        """,
        connection,
    )
    team_predictions = team_predictions.merge(match_orientation, on="source_match_id")
    team_predictions["team_probability"] = np.where(
        team_predictions["home_team"] < team_predictions["away_team"],
        team_predictions["model_probability"], 1 - team_predictions["model_probability"],
    )
    coverage = pd.read_sql_query(
        """
        SELECT d.gender, COUNT(*) individual_matches,
               SUM(r.both_ratings_available) rated_individual_matches
        FROM individual_matches i
        JOIN matches m USING(source_match_id)
        JOIN divisions d USING(division_id)
        JOIN individual_match_ratings r USING(individual_match_id)
        WHERE m.season='2025-26'
        GROUP BY d.gender
        """,
        connection,
    )
    season_counts = connection.execute(
        """
        SELECT COUNT(DISTINCT m.source_match_id), COUNT(DISTINCT i.source_match_id), COUNT(i.individual_match_id)
        FROM matches m LEFT JOIN individual_matches i USING(source_match_id)
        WHERE m.season='2025-26'
        """
    ).fetchone()
    connection.close()

    projected = pd.read_csv(PROJECT_ROOT / "data/processed/projected_lineup_backtest.csv")
    projected = projected[
        (projected["season"] == TEST_SEASON) & (projected["method"] == "most_recent")
    ].copy()
    verified = rating_evaluation["team_predictions"]
    verified = verified[verified["season"] == TEST_SEASON][[
        "source_match_id", "official_rating_lineup_probability"
    ]]
    comparison = team_predictions[[
        "source_match_id", "actual_home_won", "team_probability",
        "prior_head_to_head_matches", "elo_diff",
    ]].merge(
        projected[["source_match_id", "projected_probability"]],
        on="source_match_id", how="left",
    ).merge(verified, on="source_match_id", how="left")
    report = {
        "test_season": TEST_SEASON,
        "training_seasons": ["2019-20", "2021-22", "2022-23", "2023-24", "2024-25"],
        "methodology_frozen": True,
        "team_fold": team_fold,
        "verified_rating_fold": rating_fold,
        "comparisons": model_results(comparison),
        "coverage": {
            "team_matches": int(season_counts[0]),
            "complete_lineup_matches": int(season_counts[1]),
            "individual_matches": int(season_counts[2]),
            "complete_lineup_coverage": float(season_counts[1] / season_counts[0]),
            "fully_rated_verified_lineups": int(
                comparison["official_rating_lineup_probability"].notna().sum()
            ),
            "projectable_lineups": int(comparison["projected_probability"].notna().sum()),
            "projected_lineup_coverage_of_complete": float(
                comparison["projected_probability"].notna().sum() / season_counts[1]
            ),
            "ratings_by_gender": coverage.assign(
                rating_coverage=lambda frame: (
                    frame["rated_individual_matches"] / frame["individual_matches"]
                )
            ).to_dict(orient="records"),
        },
    }
    output = PROJECT_ROOT / "data/processed/holdout_2025_26_evaluation.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

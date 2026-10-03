from pathlib import Path
import json
import sys

import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from college_squash.database import connect_database
from college_squash.player_modeling import build_player_feature_dataset, player_walk_forward
from college_squash.modeling import build_feature_dataset, metrics, walk_forward_evaluation


def individual_diagnostics(predictions):
    frame = predictions.copy()
    frame["elo_gap_bucket"] = pd.cut(
        frame["elo_diff"].abs(), [-1, 50, 100, 200, float("inf")],
        labels=["under 50", "50-99", "100-199", "200+"], right=False,
    )
    frame["probability_bin"] = pd.cut(
        frame["player_a_probability"], [index / 10 for index in range(11)],
        include_lowest=True,
    )
    calibration = frame.groupby("probability_bin", observed=True).agg(
        matches=("player_a_win", "size"), predicted=("player_a_probability", "mean"),
        observed=("player_a_win", "mean"),
    ).reset_index()
    calibration["absolute_gap"] = (calibration["predicted"] - calibration["observed"]).abs()
    ece = float((calibration["absolute_gap"] * calibration["matches"]).sum() / len(frame))

    def grouped_metrics(column):
        rows = []
        for value, group in frame.groupby(column, observed=True):
            rows.append({column: str(value), "matches": len(group), **metrics(
                group["player_a_win"], group["player_a_probability"]
            )})
        return pd.DataFrame(rows)

    return calibration, grouped_metrics("elo_gap_bucket"), grouped_metrics("position"), ece


def compare_team_models(connection, player_evaluation):
    team_features = build_feature_dataset(connection)
    team_evaluation = walk_forward_evaluation(team_features)
    predictions = team_evaluation["predictions"].copy()
    predictions["source_match_id"] = team_features.loc[predictions.index, "source_match_id"]
    details = team_features[[
        "source_match_id", "elo_diff", "prior_head_to_head_matches", "team_a_win"
    ]]
    predictions = predictions.merge(details, on="source_match_id", suffixes=("", "_feature"))
    home_names = {
        row["source_match_id"]: (row["home_team"], row["away_team"])
        for row in connection.execute(
            """
            SELECT m.source_match_id, home.name AS home_team, away.name AS away_team
            FROM matches m
            JOIN teams home ON home.division_id=m.division_id AND home.team_id=m.home_team_id
            JOIN teams away ON away.division_id=m.division_id AND away.team_id=m.away_team_id
            """
        )
    }
    lineup = player_evaluation["team_predictions"].copy()
    lineup["lineup_probability"] = lineup.apply(
        lambda row: row["lineup_probability"]
        if home_names[row["source_match_id"]][0] < home_names[row["source_match_id"]][1]
        else 1 - row["lineup_probability"], axis=1
    )
    comparison = predictions.merge(
        lineup[["source_match_id", "lineup_probability"]], on="source_match_id"
    )
    comparison["first_time_matchup"] = comparison["prior_head_to_head_matches"] == 0
    comparison["close_matchup"] = comparison["elo_diff"].abs() < 100
    comparison["elo_upset"] = (
        ((comparison["elo_diff"] > 0) & (comparison["actual"] == 0)) |
        ((comparison["elo_diff"] < 0) & (comparison["actual"] == 1))
    )
    model_columns = {
        "win_percentage": "baseline_probability", "team_elo": "elo_probability",
        "team_logistic": "model_probability", "lineup": "lineup_probability",
    }
    report = {"coverage_matches": len(comparison), "overall": {}, "subgroups": {}}
    for name, column in model_columns.items():
        report["overall"][name] = metrics(comparison["actual"], comparison[column])
    for group_name, mask in {
        "first_time": comparison["first_time_matchup"],
        "repeat": ~comparison["first_time_matchup"],
        "close": comparison["close_matchup"],
        "elo_upset": comparison["elo_upset"],
    }.items():
        group = comparison[mask]
        report["subgroups"][group_name] = {"matches": len(group)}
        for name, column in model_columns.items():
            if len(group):
                report["subgroups"][group_name][name] = metrics(group["actual"], group[column])
    combined_rows = []
    combined_features = ["model_probability", "lineup_probability"]
    seasons = ["2021-22", "2022-23", "2023-24", "2024-25"]
    for test_season in seasons[1:]:
        test_index = seasons.index(test_season)
        train = comparison[comparison["season"].isin(seasons[:test_index])]
        test = comparison[comparison["season"] == test_season].copy()
        combined_model = make_pipeline(
            StandardScaler(), LogisticRegression(max_iter=1000, random_state=42)
        )
        combined_model.fit(train[combined_features], train["actual"])
        test["combined_probability"] = combined_model.predict_proba(
            test[combined_features]
        )[:, 1]
        combined_rows.append(test)
    combined = pd.concat(combined_rows, ignore_index=True)
    report["combined_model"] = {
        "evaluation_note": "Meta-model trains only on earlier out-of-fold seasons; 2021-22 is meta-training only.",
        "matches": len(combined),
        "team_logistic": metrics(combined["actual"], combined["model_probability"]),
        "lineup": metrics(combined["actual"], combined["lineup_probability"]),
        "combined": metrics(combined["actual"], combined["combined_probability"]),
    }
    return comparison, report


def main():
    connection = connect_database(PROJECT_ROOT / "data/college_squash.db")
    features = build_player_feature_dataset(connection)
    evaluation = player_walk_forward(features)
    calibration, elo_buckets, positions, ece = individual_diagnostics(
        evaluation["individual_predictions"]
    )
    comparison, comparison_report = compare_team_models(connection, evaluation)
    connection.close()
    output = PROJECT_ROOT / "data/processed"
    features.to_csv(output / "player_matchup_features.csv", index=False)
    evaluation["individual_predictions"].to_csv(
        output / "player_walk_forward_predictions.csv", index=False
    )
    evaluation["team_predictions"].to_csv(
        output / "lineup_walk_forward_predictions.csv", index=False
    )
    comparison.to_csv(output / "lineup_team_model_comparison.csv", index=False)
    calibration.to_csv(output / "player_model_calibration.csv", index=False)
    elo_buckets.to_csv(output / "player_model_by_elo_gap.csv", index=False)
    positions.to_csv(output / "player_model_by_position.csv", index=False)
    summary = {
        "folds": evaluation["folds"], "aggregate": evaluation["aggregate"],
        "team_model_comparison": comparison_report,
        "individual_expected_calibration_error": ece,
    }
    (output / "player_model_evaluation.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

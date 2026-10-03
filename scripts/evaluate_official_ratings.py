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
from college_squash.modeling import build_feature_dataset, metrics, walk_forward_evaluation
from college_squash.player_modeling import (
    build_player_feature_dataset, official_rating_walk_forward,
)


def calibration_error(frame, probability_column):
    bins = pd.cut(frame[probability_column], [index / 10 for index in range(11)],
                  include_lowest=True)
    table = frame.assign(probability_bin=bins).groupby(
        "probability_bin", observed=True
    ).agg(matches=("player_a_win", "size"), predicted=(probability_column, "mean"),
          observed=("player_a_win", "mean")).reset_index()
    table["absolute_gap"] = (table["predicted"] - table["observed"]).abs()
    error = float((table["matches"] * table["absolute_gap"]).sum() / len(frame))
    return table, error


def team_comparison(connection, rating_evaluation):
    features = build_feature_dataset(connection)
    team_evaluation = walk_forward_evaluation(features)
    existing = team_evaluation["predictions"].copy()
    existing["source_match_id"] = features.loc[existing.index, "source_match_id"]
    existing = existing.merge(features[[
        "source_match_id", "prior_head_to_head_matches"
    ]], on="source_match_id")
    names = {
        row["source_match_id"]: (row["home_team"], row["away_team"])
        for row in connection.execute("""
            SELECT m.source_match_id, home.name home_team, away.name away_team
            FROM matches m
            JOIN teams home ON home.division_id=m.division_id AND home.team_id=m.home_team_id
            JOIN teams away ON away.division_id=m.division_id AND away.team_id=m.away_team_id
        """)
    }
    lineups = rating_evaluation["team_predictions"].copy()
    probability_columns = [column for column in lineups if column.endswith("_lineup_probability")]
    for column in probability_columns:
        lineups[column] = lineups.apply(
            lambda row: row[column] if names[row["source_match_id"]][0] < names[row["source_match_id"]][1]
            else 1 - row[column], axis=1
        )
    comparison = existing.merge(lineups[["source_match_id", *probability_columns]],
                                on="source_match_id")
    models = {
        "team_elo": "elo_probability", "existing_team_logistic": "model_probability",
        **{column.removesuffix("_lineup_probability"): column for column in probability_columns},
    }
    report = {"matches": len(comparison), "overall": {}, "first_time": {}, "repeat": {}}
    for label, subset in {
        "overall": comparison,
        "first_time": comparison[comparison["prior_head_to_head_matches"] == 0],
        "repeat": comparison[comparison["prior_head_to_head_matches"] > 0],
    }.items():
        report[label]["matches"] = len(subset)
        for name, column in models.items():
            report[label][name] = metrics(subset["actual"], subset[column])

    # A two-input meta-model is evaluated only on earlier out-of-fold seasons.
    meta_rows = []
    meta_features = ["model_probability", "official_and_elo_lineup_probability"]
    seasons = ["2021-22", "2022-23", "2023-24", "2024-25"]
    for test_season in seasons[1:]:
        index = seasons.index(test_season)
        train = comparison[comparison["season"].isin(seasons[:index])]
        test = comparison[comparison["season"] == test_season].copy()
        if train.empty or test.empty:
            continue
        model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, random_state=42))
        model.fit(train[meta_features], train["actual"])
        test["combined_probability"] = model.predict_proba(test[meta_features])[:, 1]
        meta_rows.append(test)
    meta = pd.concat(meta_rows, ignore_index=True) if meta_rows else pd.DataFrame()
    if not meta.empty:
        report["combined"] = {
            "matches": len(meta),
            "existing_team_logistic": metrics(meta["actual"], meta["model_probability"]),
            "official_and_elo_lineup": metrics(
                meta["actual"], meta["official_and_elo_lineup_probability"]
            ),
            "combined": metrics(meta["actual"], meta["combined_probability"]),
        }
    return comparison, report


def main():
    connection = connect_database(PROJECT_ROOT / "data/college_squash.db")
    features = build_player_feature_dataset(connection)
    evaluation = official_rating_walk_forward(features)
    comparison, team_report = team_comparison(connection, evaluation)
    connection.close()

    individual = evaluation["individual_predictions"]
    diagnostics = {}
    output = PROJECT_ROOT / "data/processed"
    for model in ["player_elo", "official_rating", "official_and_elo", "previous_full"]:
        table, ece = calibration_error(individual, f"{model}_probability")
        table.to_csv(output / f"official_rating_calibration_{model}.csv", index=False)
        diagnostics[model] = {"expected_calibration_error": ece}
    individual["rating_gap_bucket"] = pd.cut(
        individual["official_rating_diff"].abs(), [-1, .25, .5, 1, float("inf")],
        labels=["under 0.25", "0.25-0.49", "0.50-0.99", "1.00+"], right=False,
    )
    grouped_rows = []
    for dimensions in [["rating_gap_bucket"], ["position"]]:
        for value, group in individual.groupby(dimensions[0], observed=True):
            row = {dimensions[0]: str(value), "matches": len(group)}
            for model in ["player_elo", "official_rating", "official_and_elo", "previous_full"]:
                result = metrics(group["player_a_win"], group[f"{model}_probability"])
                row.update({f"{model}_{key}": metric for key, metric in result.items()})
            grouped_rows.append(row)
    pd.DataFrame(grouped_rows).to_csv(output / "official_rating_model_subgroups.csv", index=False)
    individual.to_csv(output / "official_rating_individual_predictions.csv", index=False)
    evaluation["team_predictions"].to_csv(
        output / "official_rating_lineup_predictions.csv", index=False
    )
    comparison.to_csv(output / "official_rating_team_comparison.csv", index=False)
    summary = {
        "folds": evaluation["folds"], "aggregate": evaluation["aggregate"],
        "calibration": diagnostics, "team_comparison": team_report,
    }
    (output / "official_rating_evaluation.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

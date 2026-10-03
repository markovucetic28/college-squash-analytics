from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from college_squash.database import connect_database
from college_squash.modeling import (
    build_feature_dataset,
    save_model_artifact,
    walk_forward_evaluation,
)


def format_metrics(values):
    return (
        f"accuracy={values['accuracy']:.3f}, "
        f"log loss={values['log_loss']:.3f}, "
        f"Brier={values['brier_score']:.3f}"
    )


def main():
    with connect_database(PROJECT_ROOT / "data/college_squash.db") as connection:
        features = build_feature_dataset(connection)
    evaluation = walk_forward_evaluation(features)
    artifact = save_model_artifact(
        evaluation, features, PROJECT_ROOT / "data/matchup_model.joblib"
    )
    features.to_csv(
        PROJECT_ROOT / "data/processed/matchup_training_all_seasons.csv",
        index=False,
        date_format="%Y-%m-%d",
    )
    report_rows = []
    for fold in evaluation["folds"]:
        for name in ["baseline", "elo", "model"]:
            report_rows.append({
                "test_season": fold["test_season"],
                "model": name,
                "training_matches": fold["training_matches"],
                "test_matches": fold["test_matches"],
                **fold[f"{name}_metrics"],
            })
    for name in ["baseline", "elo", "model"]:
        report_rows.append({
            "test_season": "aggregate", "model": name,
            "training_matches": None,
            "test_matches": len(evaluation["predictions"]),
            **evaluation["aggregate"][name],
        })
    pd.DataFrame(report_rows).to_csv(
        PROJECT_ROOT / "data/processed/matchup_walk_forward_results.csv", index=False
    )

    for fold in evaluation["folds"]:
        print(f"{fold['test_season']}: train={fold['training_matches']}, test={fold['test_matches']}")
        for name in ["baseline", "elo", "model"]:
            print(f"  {name}: {format_metrics(fold[f'{name}_metrics'])}")
    print("Aggregate holdout performance:")
    for name in ["baseline", "elo", "model"]:
        print(f"  {name}: {format_metrics(evaluation['aggregate'][name])}")
    print(f"Final model refit on {artifact['training_matches']} matches")
    print(f"Saved {PROJECT_ROOT / 'data/matchup_model.joblib'}")


if __name__ == "__main__":
    main()

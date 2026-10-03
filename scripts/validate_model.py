from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from college_squash.database import connect_database
from college_squash.modeling import build_feature_dataset, walk_forward_evaluation
from college_squash.validation import (
    calibration_metrics,
    class_balance,
    coefficient_table,
    confidence_analysis,
    out_of_fold_matches,
    performance_by,
    reliability_analysis,
)


def save(frame, name):
    path = PROJECT_ROOT / "data/processed" / name
    frame.to_csv(path, index=False)
    return path


def main():
    with connect_database(PROJECT_ROOT / "data/college_squash.db") as connection:
        features = build_feature_dataset(connection)
    evaluation = walk_forward_evaluation(features)
    matches = out_of_fold_matches(features, evaluation)

    outputs = {
        "class balance": save(class_balance(matches), "validation_class_balance.csv"),
        "gender": save(performance_by(matches, ["gender"]), "validation_by_gender.csv"),
        "gender and season": save(
            performance_by(matches, ["season", "gender"]), "validation_by_gender_season.csv"
        ),
        "closeness": save(performance_by(matches, ["closeness"]), "validation_by_closeness.csv"),
        "closeness and season": save(
            performance_by(matches, ["season", "closeness"]),
            "validation_by_closeness_season.csv",
        ),
        "confidence": save(confidence_analysis(matches), "validation_confidence.csv"),
        "confidence and season": save(
            confidence_analysis(matches, include_season=True),
            "validation_confidence_season.csv",
        ),
        "reliability": save(reliability_analysis(matches), "validation_reliability.csv"),
        "calibration": save(calibration_metrics(matches), "validation_calibration.csv"),
        "dominant teams": save(
            performance_by(matches, ["dominant_team_involved"]),
            "validation_dominant_teams.csv",
        ),
        "dominant teams and season": save(
            performance_by(matches, ["season", "dominant_team_involved"]),
            "validation_dominant_teams_season.csv",
        ),
        "prior meetings": save(
            performance_by(matches, ["prior_meeting"]), "validation_prior_meetings.csv"
        ),
        "prior meetings and season": save(
            performance_by(matches, ["season", "prior_meeting"]),
            "validation_prior_meetings_season.csv",
        ),
        "upsets": save(
            performance_by(matches.loc[matches["elo_has_favorite"]], ["elo_upset"]),
            "validation_elo_upsets.csv",
        ),
        "upsets and season": save(
            performance_by(
                matches.loc[matches["elo_has_favorite"]], ["season", "elo_upset"]
            ),
            "validation_elo_upsets_season.csv",
        ),
        "coefficients": save(coefficient_table(evaluation), "validation_coefficients.csv"),
    }

    print("Class balance")
    print(class_balance(matches).to_string(index=False))
    print("\nAggregate performance by gender")
    print(performance_by(matches, "gender").to_string(index=False))
    print("\nAggregate performance by Elo closeness")
    print(performance_by(matches, "closeness").to_string(index=False))
    print("\nFavorite confidence")
    print(confidence_analysis(matches).to_string(index=False))
    print("\nCalibration")
    print(calibration_metrics(matches).to_string(index=False))
    print("\nDominant-team sensitivity (pre-match Elo >= 1700)")
    print(performance_by(matches, "dominant_team_involved").to_string(index=False))
    print("\nPrior matchup history")
    print(performance_by(matches, "prior_meeting").to_string(index=False))
    print("\nElo upset analysis")
    print(performance_by(matches.loc[matches["elo_has_favorite"]], "elo_upset").to_string(index=False))
    print("\nStandardized coefficients by fold")
    print(coefficient_table(evaluation).to_string(index=False))
    print("\nSaved reports")
    for label, path in outputs.items():
        print(f"{label}: {path}")


if __name__ == "__main__":
    main()

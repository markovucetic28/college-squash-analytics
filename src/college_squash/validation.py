import pandas as pd

from college_squash.modeling import FEATURE_COLUMNS, metrics


MODEL_NAMES = ["baseline", "elo", "model"]


def out_of_fold_matches(features, evaluation):
    """Join walk-forward predictions to the pre-match feature rows."""
    predictions = evaluation["predictions"]
    columns = [
        "source_match_id", "date", "season", "gender", "team_a", "team_b",
        "team_a_elo", "team_b_elo", "prior_head_to_head_matches",
        *FEATURE_COLUMNS,
    ]
    frame = features.loc[predictions.index, columns].copy()
    for column in ["actual", "baseline_probability", "elo_probability", "model_probability"]:
        frame[column] = predictions[column]
    return add_validation_groups(frame)


def add_validation_groups(frame):
    frame = frame.copy()
    elo_gap = frame["elo_diff"].abs()
    frame["closeness"] = pd.cut(
        elo_gap,
        bins=[-0.001, 50, 100, 200, float("inf")],
        labels=["Very close (<50)", "Moderately close (50-99)",
                "Clear favorite (100-199)", "Heavy favorite (200+)"]
    )
    confidence = frame["model_probability"].where(
        frame["model_probability"] >= 0.5, 1 - frame["model_probability"]
    )
    frame["favorite_confidence"] = confidence
    frame["confidence_bucket"] = pd.cut(
        confidence,
        bins=[0.5, 0.6, 0.7, 0.8, 0.9, 1.000001],
        labels=["50-60%", "60-70%", "70-80%", "80-90%", "90-100%"],
        include_lowest=True,
        right=False,
    )
    frame["model_favorite_won"] = (
        (frame["model_probability"] >= 0.5) == frame["actual"].astype(bool)
    )
    frame["dominant_team_involved"] = frame[["team_a_elo", "team_b_elo"]].max(axis=1) >= 1700
    frame["prior_meeting"] = frame["prior_head_to_head_matches"] > 0
    frame["elo_has_favorite"] = frame["team_a_elo"] != frame["team_b_elo"]
    frame["elo_favorite_won"] = (
        (frame["team_a_elo"] > frame["team_b_elo"]) == frame["actual"].astype(bool)
    )
    frame["elo_upset"] = frame["elo_has_favorite"] & ~frame["elo_favorite_won"]
    return frame


def class_balance(frame):
    rows = []
    for season, group in frame.groupby("season", sort=False):
        wins = int(group["actual"].sum())
        rows.append({
            "season": season, "matches": len(group), "team_a_wins": wins,
            "team_a_losses": len(group) - wins, "team_a_win_rate": wins / len(group),
        })
    return pd.DataFrame(rows)


def performance_by(frame, group_columns):
    if isinstance(group_columns, str):
        group_columns = [group_columns]
    rows = []
    observed_groups = frame.groupby(group_columns, observed=True, sort=False)
    for values, group in observed_groups:
        if not isinstance(values, tuple):
            values = (values,)
        common = dict(zip(group_columns, values))
        for model_name in MODEL_NAMES:
            result = metrics(group["actual"], group[f"{model_name}_probability"])
            rows.append({**common, "model": model_name, "matches": len(group), **result})
    return pd.DataFrame(rows)


def confidence_analysis(frame, include_season=False):
    groups = ["confidence_bucket"]
    if include_season:
        groups.insert(0, "season")
    rows = []
    for values, group in frame.groupby(groups, observed=True, sort=False):
        if not isinstance(values, tuple):
            values = (values,)
        rows.append({
            **dict(zip(groups, values)),
            "matches": len(group),
            "mean_confidence": group["favorite_confidence"].mean(),
            "favorite_win_rate": group["model_favorite_won"].mean(),
            "calibration_gap": group["model_favorite_won"].mean()
            - group["favorite_confidence"].mean(),
        })
    return pd.DataFrame(rows)


def reliability_analysis(frame, include_season=False):
    frame = frame.copy()
    frame["probability_bucket"] = pd.cut(
        frame["model_probability"],
        bins=[value / 10 for value in range(11)],
        include_lowest=True,
    )
    groups = ["probability_bucket"]
    if include_season:
        groups.insert(0, "season")
    rows = []
    for values, group in frame.groupby(groups, observed=True, sort=False):
        if not isinstance(values, tuple):
            values = (values,)
        predicted = group["model_probability"].mean()
        observed = group["actual"].mean()
        rows.append({
            **dict(zip(groups, values)), "matches": len(group),
            "mean_predicted_probability": predicted,
            "observed_team_a_win_rate": observed,
            "absolute_gap": abs(observed - predicted),
        })
    result = pd.DataFrame(rows)
    if include_season:
        totals = result.groupby("season")["matches"].transform("sum")
        result["ece_contribution"] = result["matches"] / totals * result["absolute_gap"]
    else:
        result["ece_contribution"] = result["matches"] / len(frame) * result["absolute_gap"]
    return result


def calibration_metrics(frame):
    rows = []
    for season, group in [("aggregate", frame), *frame.groupby("season", sort=False)]:
        reliability = reliability_analysis(group)
        rows.append({
            "season": season,
            "matches": len(group),
            "expected_calibration_error": reliability["ece_contribution"].sum(),
            "maximum_calibration_error": reliability["absolute_gap"].max(),
        })
    return pd.DataFrame(rows)


def coefficient_table(evaluation):
    rows = []
    for fold in evaluation["folds"]:
        rows.append({"test_season": fold["test_season"], **fold["coefficients"]})
    table = pd.DataFrame(rows)
    mean_row = {"test_season": "mean"}
    mean_row.update({column: table[column].mean() for column in FEATURE_COLUMNS})
    return pd.concat([table, pd.DataFrame([mean_row])], ignore_index=True)

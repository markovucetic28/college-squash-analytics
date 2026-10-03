from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from college_squash.database import connect_database
from college_squash.lineup_projection import (
    build_historical_projections, lineup_agreement, rating_before, rating_lookup,
)
from college_squash.modeling import SEASONS, build_feature_dataset, metrics, walk_forward_evaluation
from college_squash.player_modeling import (
    OFFICIAL_RATING_FEATURES, build_player_feature_dataset,
    official_rating_walk_forward, probability_at_least_five,
)


CONFIDENCE_THRESHOLD = 0.75


def model_pipeline():
    return make_pipeline(
        StandardScaler(), LogisticRegression(max_iter=1000, random_state=42)
    )


def load_lineup_rows(connection):
    return pd.read_sql_query(
        """
        SELECT i.source_match_id, m.match_date, m.season, d.gender, i.position,
               'home' side, home.program_id, i.home_player_id player_id
        FROM individual_matches i
        JOIN matches m USING(source_match_id)
        JOIN divisions d USING(division_id)
        JOIN teams home ON home.division_id=m.division_id AND home.team_id=m.home_team_id
        UNION ALL
        SELECT i.source_match_id, m.match_date, m.season, d.gender, i.position,
               'away' side, away.program_id, i.away_player_id player_id
        FROM individual_matches i
        JOIN matches m USING(source_match_id)
        JOIN divisions d USING(division_id)
        JOIN teams away ON away.division_id=m.division_id AND away.team_id=m.away_team_id
        ORDER BY match_date, source_match_id, side, position
        """,
        connection,
    )


def add_roster_projection(connection, lineup_rows, projections):
    roster = pd.read_sql_query(
        """
        SELECT d.season, t.program_id, CAST(p.roster_position AS INTEGER) position,
               p.player_id
        FROM player_team_seasons p
        JOIN divisions d USING(division_id)
        JOIN teams t USING(division_id, team_id)
        WHERE CAST(p.roster_position AS INTEGER) BETWEEN 1 AND 9
        ORDER BY d.season, t.program_id, position
        """,
        connection,
    )
    roster_lineups = {
        (season, int(program_id)): group.sort_values("position")["player_id"].astype(int).tolist()
        for (season, program_id), group in roster.groupby(["season", "program_id"])
        if len(group) == 9 and group["position"].nunique() == 9
    }
    actual = lineup_rows.groupby(
        ["source_match_id", "match_date", "season", "side", "program_id"]
    )["player_id"].apply(list).reset_index(name="actual_lineup")
    rows = []
    for row in actual.itertuples(index=False):
        projected = roster_lineups.get((row.season, int(row.program_id)))
        agreement = lineup_agreement(projected, row.actual_lineup)
        rows.append({
            "source_match_id": int(row.source_match_id),
            "match_date": pd.Timestamp(row.match_date), "side": row.side,
            "program_id": int(row.program_id), "method": "roster_order",
            "projected_lineup": projected, "actual_lineup": row.actual_lineup,
            "prior_complete_lineups": 0, "confidence": np.nan, **agreement,
        })
    return pd.concat([projections, pd.DataFrame(rows)], ignore_index=True)


def train_rating_models(player_features):
    models = {}
    for test_season in SEASONS[1:]:
        split = SEASONS.index(test_season)
        train = player_features[
            player_features["season"].isin(SEASONS[:split])
            & player_features["official_rating_diff"].notna()
        ]
        model = model_pipeline()
        model.fit(train[OFFICIAL_RATING_FEATURES], train["player_a_win"])
        models[test_season] = model
    return models


def projected_probability(row, model, ratings):
    probabilities = []
    for position, (home_id, away_id) in enumerate(
        zip(row.home_projected_lineup, row.away_projected_lineup), start=1
    ):
        home_rating = rating_before(ratings, home_id, row.match_date)
        away_rating = rating_before(ratings, away_id, row.match_date)
        if home_rating is None or away_rating is None:
            return None
        if home_id < away_id:
            difference, home_is_a = home_rating - away_rating, True
        else:
            difference, home_is_a = away_rating - home_rating, False
        player_a_probability = model.predict_proba(
            pd.DataFrame([{"official_rating_diff": difference, "position": position}])
        )[0, 1]
        probabilities.append(
            float(player_a_probability if home_is_a else 1 - player_a_probability)
        )
    return probability_at_least_five(probabilities)


def pair_projections(projections, match_details, models, ratings):
    home = projections[projections["side"] == "home"].rename(columns={
        column: f"home_{column}" for column in [
            "projected_lineup", "actual_lineup", "prior_complete_lineups", "confidence",
            "correct_players", "correct_positions", "all_players_correct",
        ]
    })
    away = projections[projections["side"] == "away"].rename(columns={
        column: f"away_{column}" for column in [
            "projected_lineup", "actual_lineup", "prior_complete_lineups", "confidence",
            "correct_players", "correct_positions", "all_players_correct",
        ]
    })
    paired = home.merge(
        away.drop(columns=["match_date", "program_id", "side"]),
        on=["source_match_id", "method"], how="inner",
    ).merge(
        match_details.drop(columns=["match_date"]), on="source_match_id", how="left"
    )
    paired["projection_available"] = (
        paired["home_projected_lineup"].notna()
        & paired["away_projected_lineup"].notna()
    )
    paired["projected_probability"] = np.nan
    held_out = paired["season"].isin(SEASONS[1:]) & paired["projection_available"]
    for index, row in paired[held_out].iterrows():
        paired.at[index, "projected_probability"] = projected_probability(
            row, models[row["season"]], ratings
        )
    paired["all_18_players_correct"] = (
        paired["home_all_players_correct"] & paired["away_all_players_correct"]
    )
    paired["average_correct_players"] = (
        paired["home_correct_players"] + paired["away_correct_players"]
    ) / 2
    paired["average_correct_positions"] = (
        paired["home_correct_positions"] + paired["away_correct_positions"]
    ) / 2
    paired["lineup_confidence"] = paired[["home_confidence", "away_confidence"]].min(axis=1)
    return paired


def team_predictions(connection):
    features = build_feature_dataset(connection)
    evaluation = walk_forward_evaluation(features)
    predictions = evaluation["predictions"].copy()
    predictions["source_match_id"] = features.loc[predictions.index, "source_match_id"]
    predictions["prior_head_to_head_matches"] = features.loc[
        predictions.index, "prior_head_to_head_matches"
    ]
    predictions["elo_diff"] = features.loc[predictions.index, "elo_diff"]
    names = pd.read_sql_query(
        """
        SELECT m.source_match_id, m.season, m.match_date,
               home.name home_team, away.name away_team,
               CASE WHEN m.home_score > m.away_score THEN 1 ELSE 0 END actual_home_won
        FROM matches m
        JOIN teams home ON home.division_id=m.division_id AND home.team_id=m.home_team_id
        JOIN teams away ON away.division_id=m.division_id AND away.team_id=m.away_team_id
        """,
        connection,
    )
    predictions = predictions.drop(columns=["season"]).merge(names, on="source_match_id")
    predictions["team_probability"] = np.where(
        predictions["home_team"] < predictions["away_team"],
        predictions["model_probability"], 1 - predictions["model_probability"],
    )
    return predictions[[
        "source_match_id", "season", "match_date", "actual_home_won", "team_probability",
        "prior_head_to_head_matches", "elo_diff",
    ]]


def summarize(frame, probability_column):
    available = frame[frame[probability_column].notna()].copy()
    if available.empty:
        return {"matches": 0, "accuracy": None, "log_loss": None, "brier_score": None}
    return {
        "matches": len(available),
        **metrics(available["actual_home_won"], available[probability_column]),
    }


def main():
    connection = connect_database(PROJECT_ROOT / "data/college_squash.db")
    lineup_rows = load_lineup_rows(connection)
    projections = build_historical_projections(lineup_rows)
    projections = add_roster_projection(connection, lineup_rows, projections)
    player_features = build_player_feature_dataset(connection)
    models = train_rating_models(player_features)
    ratings = rating_lookup(pd.read_sql_query(
        "SELECT player_id, rating_date, rating FROM player_ratings", connection
    ))
    team = team_predictions(connection)
    paired = pair_projections(projections, team, models, ratings)
    verified = official_rating_walk_forward(player_features)["team_predictions"][
        ["source_match_id", "official_rating_lineup_probability"]
    ]
    connection.close()
    paired = paired.merge(verified, on="source_match_id", how="left")

    held_out = paired[paired["season"].isin(SEASONS[1:])].copy()
    report = {"confidence_threshold": CONFIDENCE_THRESHOLD, "methods": {}}
    for method, group in held_out.groupby("method"):
        available = group[group["projected_probability"].notna()].copy()
        lineup_units = pd.concat([
            available[["home_correct_players", "home_correct_positions", "home_all_players_correct"]]
            .rename(columns=lambda column: column.removeprefix("home_")),
            available[["away_correct_players", "away_correct_positions", "away_all_players_correct"]]
            .rename(columns=lambda column: column.removeprefix("away_")),
        ])
        report["methods"][method] = {
            "eligible_held_out_matches": int(len(group)),
            "projection_coverage": float(len(available) / len(group)),
            "projectable_matches": len(available),
            "all_9_players_correct": float(lineup_units["all_players_correct"].mean()),
            "both_teams_all_9_correct": float(available["all_18_players_correct"].mean()),
            "average_correct_players": float(lineup_units["correct_players"].mean()),
            "average_correct_positions": float(lineup_units["correct_positions"].mean()),
            "projected_metrics": summarize(available, "projected_probability"),
            "verified_metrics_same_matches": summarize(
                available, "official_rating_lineup_probability"
            ),
            "team_metrics_same_matches": summarize(available, "team_probability"),
            "first_time": summarize(
                available[available["prior_head_to_head_matches"] == 0],
                "projected_probability",
            ),
            "first_time_verified": summarize(
                available[available["prior_head_to_head_matches"] == 0],
                "official_rating_lineup_probability",
            ),
            "first_time_team": summarize(
                available[available["prior_head_to_head_matches"] == 0],
                "team_probability",
            ),
        }

    primary = held_out[held_out["method"] == "most_recent"].copy()
    primary["use_projected"] = (
        primary["projected_probability"].notna()
        & (primary["lineup_confidence"] >= CONFIDENCE_THRESHOLD)
    )
    primary["fallback_probability"] = np.where(
        primary["use_projected"], primary["projected_probability"], primary["team_probability"]
    )
    projectable = primary[primary["projected_probability"].notna()].copy()
    projectable["missing_players_per_team"] = 9 - projectable["average_correct_players"]
    projectable["shared_players_in_wrong_position"] = (
        projectable["average_correct_players"] - projectable["average_correct_positions"]
    )
    stability = {}
    for label, subset in {
        "higher_confidence": projectable[projectable["lineup_confidence"] >= CONFIDENCE_THRESHOLD],
        "lower_confidence": projectable[projectable["lineup_confidence"] < CONFIDENCE_THRESHOLD],
    }.items():
        stability[label] = {
            "matches": len(subset),
            "average_correct_players": float(subset["average_correct_players"].mean()),
            "average_correct_positions": float(subset["average_correct_positions"].mean()),
            "projected_metrics": summarize(subset, "projected_probability"),
            "team_metrics": summarize(subset, "team_probability"),
        }
    by_season = {}
    for season, subset in primary.groupby("season"):
        by_season[season] = {
            "projected": summarize(subset, "projected_probability"),
            "fallback": summarize(subset, "fallback_probability"),
            "team": summarize(subset, "team_probability"),
        }
    report["prospective_mode"] = {
        "definition": "Most recent complete lineup; team model below fixed 0.75 confidence or when a rating is missing.",
        "matches": len(primary),
        "projected_used": int(primary["use_projected"].sum()),
        "fallback_used": int((~primary["use_projected"]).sum()),
        "fallback_metrics": summarize(primary, "fallback_probability"),
        "team_only_metrics": summarize(primary, "team_probability"),
        "first_time_fallback_metrics": summarize(
            primary[primary["prior_head_to_head_matches"] == 0], "fallback_probability"
        ),
        "first_time_team_metrics": summarize(
            primary[primary["prior_head_to_head_matches"] == 0], "team_probability"
        ),
        "average_missing_players_per_team": float(
            projectable["missing_players_per_team"].mean()
        ),
        "average_shared_players_in_wrong_position": float(
            projectable["shared_players_in_wrong_position"].mean()
        ),
        "stability": stability,
        "by_season": by_season,
    }

    output = PROJECT_ROOT / "data/processed"
    projections.to_csv(output / "historical_lineup_projections.csv", index=False)
    paired.to_csv(output / "projected_lineup_backtest.csv", index=False)
    (output / "projected_lineup_evaluation.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

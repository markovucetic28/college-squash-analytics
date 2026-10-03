from collections import defaultdict
from pathlib import Path

import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


SEASONS = ["2019-20", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
HISTORY_DECAY = 0.60
TRAINING_DECAY = 0.75
ELO_CARRYOVER = 0.75
ELO_START = 1500.0
ELO_K = 20.0

FEATURE_COLUMNS = [
    "current_win_percentage_diff",
    "prior_season_strength_diff",
    "recent_form_diff",
    "average_margin_diff",
    "strength_of_schedule_diff",
    "elo_diff",
    "head_to_head_diff",
]


def _empty_state():
    return {"wins": 0, "matches": 0, "margins": [], "recent": [], "opponents": []}


def _win_percentage(state):
    return (state["wins"] + 1) / (state["matches"] + 2)


def _recent_percentage(state):
    recent = state["recent"][-5:]
    return (sum(recent) + 1) / (len(recent) + 2)


def _average_margin(state):
    return sum(state["margins"]) / len(state["margins"]) if state["margins"] else 0.0


def _schedule_strength(state, states):
    if not state["opponents"]:
        return 0.5
    return sum(_win_percentage(states[opponent]) for opponent in state["opponents"]) / len(
        state["opponents"]
    )


def decayed_program_strength(season_win_percentages, decay=HISTORY_DECAY):
    """Weight the most recent completed season most heavily."""
    if not season_win_percentages:
        return 0.5
    weights = [decay ** age for age in reversed(range(len(season_win_percentages)))]
    return sum(value * weight for value, weight in zip(season_win_percentages, weights)) / sum(weights)


def elo_probability(rating_a, rating_b):
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))


def elo_changes(rating_a, rating_b, team_a_won, k_factor=ELO_K):
    expected = elo_probability(rating_a, rating_b)
    change = k_factor * (team_a_won - expected)
    return change, -change


def regress_elo(rating, carryover=ELO_CARRYOVER):
    return ELO_START + carryover * (rating - ELO_START)


def _head_to_head_advantage(team_a, team_b, head_to_head):
    a_wins = head_to_head[(team_a, team_b)]
    b_wins = head_to_head[(team_b, team_a)]
    probability = (a_wins + 1) / (a_wins + b_wins + 2)
    return (2 * probability) - 1


def _match_rows(connection):
    return connection.execute(
        """
        SELECT m.source_match_id, m.match_date, m.season, d.gender,
               home.program_id AS home_program_id, home.name AS home_team,
               away.program_id AS away_program_id, away.name AS away_team,
               m.home_score, m.away_score
        FROM matches m
        JOIN divisions d ON d.division_id=m.division_id
        JOIN teams home ON home.division_id=m.division_id AND home.team_id=m.home_team_id
        JOIN teams away ON away.division_id=m.division_id AND away.team_id=m.away_team_id
        ORDER BY m.match_date, m.source_match_id
        """
    ).fetchall()


def _feature_values(team_a, team_b, states, season_history, elo, head_to_head):
    state_a, state_b = states[team_a], states[team_b]
    values_a = {
        "current_win_percentage": _win_percentage(state_a),
        "prior_season_strength": decayed_program_strength(season_history[team_a]),
        "recent_form": _recent_percentage(state_a),
        "average_margin": _average_margin(state_a),
        "strength_of_schedule": _schedule_strength(state_a, states),
        "elo": elo[team_a],
    }
    values_b = {
        "current_win_percentage": _win_percentage(state_b),
        "prior_season_strength": decayed_program_strength(season_history[team_b]),
        "recent_form": _recent_percentage(state_b),
        "average_margin": _average_margin(state_b),
        "strength_of_schedule": _schedule_strength(state_b, states),
        "elo": elo[team_b],
    }
    differences = {f"{name}_diff": values_a[name] - values_b[name] for name in values_a}
    differences["head_to_head_diff"] = _head_to_head_advantage(team_a, team_b, head_to_head)
    return values_a, values_b, differences


def _finish_season(states, season_history, elo, head_to_head):
    for program, state in states.items():
        if state["matches"]:
            season_history[program].append(state["wins"] / state["matches"])
    for program in list(elo):
        elo[program] = regress_elo(elo[program])
    for pairing in list(head_to_head):
        head_to_head[pairing] *= HISTORY_DECAY


def build_feature_dataset(connection):
    """Create one strictly pre-match feature row per verified match."""
    rows = _match_rows(connection)
    rows_by_season = defaultdict(list)
    for row in rows:
        rows_by_season[row["season"]].append(row)

    season_history = defaultdict(list)
    elo = defaultdict(lambda: ELO_START)
    head_to_head = defaultdict(float)
    feature_rows = []

    for season in SEASONS:
        states = defaultdict(_empty_state)
        matches_by_date = defaultdict(list)
        for match in rows_by_season[season]:
            matches_by_date[match["match_date"]].append(match)

        for match_date in sorted(matches_by_date):
            date_matches = matches_by_date[match_date]
            for match in date_matches:
                home_key, away_key = match["home_program_id"], match["away_program_id"]
                if match["home_team"] < match["away_team"]:
                    team_a_key, team_b_key = home_key, away_key
                    team_a, team_b = match["home_team"], match["away_team"]
                    team_a_won = int(match["home_score"] > match["away_score"])
                else:
                    team_a_key, team_b_key = away_key, home_key
                    team_a, team_b = match["away_team"], match["home_team"]
                    team_a_won = int(match["away_score"] > match["home_score"])
                values_a, values_b, differences = _feature_values(
                    team_a_key, team_b_key, states, season_history, elo, head_to_head
                )
                prior_meetings = (
                    head_to_head[(team_a_key, team_b_key)]
                    + head_to_head[(team_b_key, team_a_key)]
                )
                feature_rows.append({
                    "source_match_id": match["source_match_id"], "date": match_date,
                    "season": season, "gender": match["gender"],
                    "team_a": team_a, "team_b": team_b,
                    "team_a_program_id": team_a_key, "team_b_program_id": team_b_key,
                    "team_a_prior_matches": states[team_a_key]["matches"],
                    "team_b_prior_matches": states[team_b_key]["matches"],
                    "prior_head_to_head_matches": prior_meetings,
                    **{f"team_a_{name}": value for name, value in values_a.items()},
                    **{f"team_b_{name}": value for name, value in values_b.items()},
                    **differences, "team_a_win": team_a_won,
                })

            # Freeze all information within a date, then apply every result.
            elo_deltas = defaultdict(float)
            for match in date_matches:
                home, away = match["home_program_id"], match["away_program_id"]
                home_won = int(match["home_score"] > match["away_score"])
                margin = match["home_score"] - match["away_score"]
                for key, opponent, won, team_margin in [
                    (home, away, home_won, margin), (away, home, 1 - home_won, -margin)
                ]:
                    states[key]["wins"] += won
                    states[key]["matches"] += 1
                    states[key]["margins"].append(team_margin)
                    states[key]["recent"].append(won)
                    states[key]["opponents"].append(opponent)
                winner, loser = (home, away) if home_won else (away, home)
                head_to_head[(winner, loser)] += 1
                home_change, away_change = elo_changes(elo[home], elo[away], home_won)
                elo_deltas[home] += home_change
                elo_deltas[away] += away_change
            for program, change in elo_deltas.items():
                elo[program] += change
        _finish_season(states, season_history, elo, head_to_head)

    features = pd.DataFrame(feature_rows)
    features["date"] = pd.to_datetime(features["date"])
    return features


def baseline_probabilities(features):
    return (0.5 + 0.5 * features["current_win_percentage_diff"]).clip(0.05, 0.95)


def elo_probabilities(features):
    return features.apply(
        lambda row: elo_probability(row["team_a_elo"], row["team_b_elo"]), axis=1
    ).clip(0.05, 0.95)


def metrics(actual, probabilities):
    predictions = (probabilities >= 0.5).astype(int)
    return {
        "accuracy": float(accuracy_score(actual, predictions)),
        "log_loss": float(log_loss(actual, probabilities, labels=[0, 1])),
        "brier_score": float(brier_score_loss(actual, probabilities)),
    }


def recency_weights(train, test_season, decay=TRAINING_DECAY):
    test_index = SEASONS.index(test_season)
    return train["season"].map(
        lambda season: decay ** (test_index - 1 - SEASONS.index(season))
    ).astype(float)


def _new_model():
    return make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, random_state=42))


def walk_forward_evaluation(features):
    folds, predictions = [], []
    for test_season in SEASONS[1:]:
        test_index = SEASONS.index(test_season)
        train_seasons = SEASONS[:test_index]
        train = features.loc[features["season"].isin(train_seasons)].copy()
        test = features.loc[features["season"] == test_season].copy()
        model = _new_model()
        model.fit(
            train[FEATURE_COLUMNS], train["team_a_win"],
            logisticregression__sample_weight=recency_weights(train, test_season),
        )
        probabilities = {
            "baseline": baseline_probabilities(test),
            "elo": elo_probabilities(test),
            "model": pd.Series(model.predict_proba(test[FEATURE_COLUMNS])[:, 1], index=test.index),
        }
        fold = {"test_season": test_season, "training_matches": len(train),
                "test_matches": len(test),
                "coefficients": dict(zip(
                    FEATURE_COLUMNS,
                    model.named_steps["logisticregression"].coef_[0].astype(float),
                ))}
        for name, values in probabilities.items():
            fold[f"{name}_metrics"] = metrics(test["team_a_win"], values)
        folds.append(fold)
        prediction_frame = pd.DataFrame({
            "actual": test["team_a_win"], "season": test_season,
            **{f"{name}_probability": values for name, values in probabilities.items()},
        })
        predictions.append(prediction_frame)

    combined = pd.concat(predictions).sort_index()
    aggregate = {
        name: metrics(combined["actual"], combined[f"{name}_probability"])
        for name in ["baseline", "elo", "model"]
    }
    return {"folds": folds, "aggregate": aggregate, "predictions": combined}


def save_model_artifact(evaluation, features, output_path):
    final_model = _new_model()
    weights = features["season"].map(
        lambda season: TRAINING_DECAY ** (len(SEASONS) - 1 - SEASONS.index(season))
    ).astype(float)
    final_model.fit(
        features[FEATURE_COLUMNS], features["team_a_win"],
        logisticregression__sample_weight=weights,
    )
    artifact = {
        "model": final_model,
        "feature_columns": FEATURE_COLUMNS,
        "seasons": SEASONS,
        "history_decay": HISTORY_DECAY,
        "training_decay": TRAINING_DECAY,
        "elo_carryover": ELO_CARRYOVER,
        "training_matches": len(features),
        "walk_forward_folds": evaluation["folds"],
        "aggregate_metrics": evaluation["aggregate"],
        "trained_through": features["date"].max().strftime("%Y-%m-%d"),
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, output_path)
    return artifact


def current_matchup_features(connection, team_one, team_two, gender):
    rows = _match_rows(connection)
    program_names = {}
    for row in rows:
        if row["gender"] == gender:
            program_names[row["home_team"]] = row["home_program_id"]
            program_names[row["away_team"]] = row["away_program_id"]
    if team_one not in program_names or team_two not in program_names:
        raise ValueError("Both teams must have verified historical matches")

    # Reconstruct the post-2024-25 state from the final pre-match rows plus results.
    # Calling the feature builder already validates chronological ordering; replaying
    # here keeps prediction behavior identical and easy to inspect.
    season_history = defaultdict(list)
    elo = defaultdict(lambda: ELO_START)
    head_to_head = defaultdict(float)
    all_rows = _match_rows(connection)
    for season in SEASONS:
        states = defaultdict(_empty_state)
        dates = defaultdict(list)
        for row in all_rows:
            if row["season"] == season:
                dates[row["match_date"]].append(row)
        for match_date in sorted(dates):
            deltas = defaultdict(float)
            for match in dates[match_date]:
                home, away = match["home_program_id"], match["away_program_id"]
                home_won = int(match["home_score"] > match["away_score"])
                margin = match["home_score"] - match["away_score"]
                for key, opponent, won, team_margin in [
                    (home, away, home_won, margin), (away, home, 1-home_won, -margin)
                ]:
                    states[key]["wins"] += won; states[key]["matches"] += 1
                    states[key]["margins"].append(team_margin); states[key]["recent"].append(won)
                    states[key]["opponents"].append(opponent)
                winner, loser = (home, away) if home_won else (away, home)
                head_to_head[(winner, loser)] += 1
                a, b = elo_changes(elo[home], elo[away], home_won)
                deltas[home] += a; deltas[away] += b
            for program, change in deltas.items():
                elo[program] += change
        _finish_season(states, season_history, elo, head_to_head)

    # A future matchup begins a new season: current-season statistics are neutral,
    # while prior strength, decayed head-to-head, and carried Elo retain history.
    states = defaultdict(_empty_state)
    first, second = program_names[team_one], program_names[team_two]
    if team_one < team_two:
        a, b, requested_is_a = first, second, True
    else:
        a, b, requested_is_a = second, first, False
    _, _, differences = _feature_values(a, b, states, season_history, elo, head_to_head)
    return pd.DataFrame([differences], columns=FEATURE_COLUMNS), requested_is_a


def predict_matchup(connection, artifact, team_one, team_two, gender):
    features, requested_is_a = current_matchup_features(connection, team_one, team_two, gender)
    probability_a = artifact["model"].predict_proba(features)[0, 1]
    return float(probability_a if requested_is_a else 1 - probability_a)

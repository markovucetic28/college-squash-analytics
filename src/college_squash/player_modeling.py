from collections import defaultdict
import json

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from college_squash.modeling import SEASONS, elo_changes, elo_probability, metrics


PLAYER_ELO_START = 1500.0
PLAYER_ELO_K = 20.0
PLAYER_ELO_CARRYOVER = 0.75
PLAYER_FEATURES = [
    "elo_diff", "win_percentage_diff", "recent_form_diff", "head_to_head_diff", "position"
]
OFFICIAL_RATING_FEATURES = ["official_rating_diff", "position"]
OFFICIAL_AND_ELO_FEATURES = ["official_rating_diff", "elo_diff", "position"]


def _state():
    return {"wins": 0, "matches": 0, "recent": []}


def _rate(state, recent=False):
    values = state["recent"][-5:] if recent else None
    if recent:
        return (sum(values) + 1) / (len(values) + 2)
    return (state["wins"] + 1) / (state["matches"] + 2)


def _individual_rows(connection):
    has_ratings = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='individual_match_ratings'"
    ).fetchone()
    rating_columns = (
        "r.home_rating, r.away_rating, r.home_rating_date, r.away_rating_date, "
        "r.home_rating_age_days, r.away_rating_age_days"
        if has_ratings else
        "NULL home_rating, NULL away_rating, NULL home_rating_date, NULL away_rating_date, "
        "NULL home_rating_age_days, NULL away_rating_age_days"
    )
    rating_join = (
        "LEFT JOIN individual_match_ratings r "
        "ON r.individual_match_id=i.individual_match_id"
        if has_ratings else ""
    )
    return connection.execute(
        f"""
        SELECT i.individual_match_id, i.source_match_id, i.position,
               i.home_player_id, i.away_player_id, i.winner_side,
               m.match_date, m.season, d.gender,
               {rating_columns}
        FROM individual_matches i
        JOIN matches m ON m.source_match_id=i.source_match_id
        JOIN divisions d ON d.division_id=m.division_id
        {rating_join}
        ORDER BY m.match_date, m.source_match_id, i.position
        """
    ).fetchall()


def build_player_feature_dataset(connection):
    """Build pre-match player features, freezing all updates within each date."""
    rows_by_season = defaultdict(list)
    for row in _individual_rows(connection):
        rows_by_season[row["season"]].append(row)
    states = defaultdict(_state)
    ratings = defaultdict(lambda: PLAYER_ELO_START)
    head_to_head = defaultdict(float)
    output = []
    for season in SEASONS:
        by_date = defaultdict(list)
        for row in rows_by_season[season]:
            by_date[row["match_date"]].append(row)
        for match_date in sorted(by_date):
            day = by_date[match_date]
            for row in day:
                home, away = row["home_player_id"], row["away_player_id"]
                if home < away:
                    player_a, player_b = home, away
                    player_a_won = int(row["winner_side"] == "H")
                else:
                    player_a, player_b = away, home
                    player_a_won = int(row["winner_side"] == "V")
                a_state, b_state = states[player_a], states[player_b]
                a_h2h, b_h2h = head_to_head[(player_a, player_b)], head_to_head[(player_b, player_a)]
                output.append({
                    "individual_match_id": row["individual_match_id"],
                    "source_match_id": row["source_match_id"], "date": match_date,
                    "season": season, "gender": row["gender"], "position": row["position"],
                    "home_player_id": home, "away_player_id": away,
                    "player_a_id": player_a, "player_b_id": player_b,
                    "player_a_elo": ratings[player_a], "player_b_elo": ratings[player_b],
                    "elo_diff": ratings[player_a] - ratings[player_b],
                    "official_rating_diff": (
                        None if row["home_rating"] is None or row["away_rating"] is None
                        else row["home_rating"] - row["away_rating"]
                        if player_a == home else row["away_rating"] - row["home_rating"]
                    ),
                    "home_rating": row["home_rating"], "away_rating": row["away_rating"],
                    "home_rating_date": row["home_rating_date"],
                    "away_rating_date": row["away_rating_date"],
                    "home_rating_age_days": row["home_rating_age_days"],
                    "away_rating_age_days": row["away_rating_age_days"],
                    "win_percentage_diff": _rate(a_state) - _rate(b_state),
                    "recent_form_diff": _rate(a_state, True) - _rate(b_state, True),
                    "head_to_head_diff": (a_h2h - b_h2h) / (a_h2h + b_h2h + 2),
                    "prior_head_to_head_matches": a_h2h + b_h2h,
                    "player_a_win": player_a_won,
                })
            changes = defaultdict(float)
            for row in day:
                home, away = row["home_player_id"], row["away_player_id"]
                home_won = int(row["winner_side"] == "H")
                for player, won in [(home, home_won), (away, 1 - home_won)]:
                    states[player]["wins"] += won
                    states[player]["matches"] += 1
                    states[player]["recent"].append(won)
                winner, loser = (home, away) if home_won else (away, home)
                head_to_head[(winner, loser)] += 1
                home_change, away_change = elo_changes(
                    ratings[home], ratings[away], home_won, PLAYER_ELO_K
                )
                changes[home] += home_change
                changes[away] += away_change
            for player, change in changes.items():
                ratings[player] += change
        for player in list(ratings):
            ratings[player] = PLAYER_ELO_START + PLAYER_ELO_CARRYOVER * (
                ratings[player] - PLAYER_ELO_START
            )
    frame = pd.DataFrame(output)
    if not frame.empty:
        frame["date"] = pd.to_datetime(frame["date"])
    return frame


def lineup_score_distribution(probabilities):
    """Exact probabilities for winning zero through nine individual matches."""
    if len(probabilities) != 9:
        raise ValueError("A varsity lineup must contain exactly nine probabilities")
    distribution = np.array([1.0])
    for probability in probabilities:
        if not 0 <= probability <= 1:
            raise ValueError("Probabilities must be between zero and one")
        distribution = np.convolve(distribution, [1 - probability, probability])
    return distribution


def probability_at_least_five(probabilities):
    """Exact Poisson-binomial probability of winning at least five of nine."""
    probability = float(lineup_score_distribution(probabilities)[5:].sum())
    return min(1.0, max(0.0, probability))


def expected_individual_wins(probabilities):
    if len(probabilities) != 9:
        raise ValueError("A varsity lineup must contain exactly nine probabilities")
    return float(sum(probabilities))


def _model():
    return make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, random_state=42))


def player_walk_forward(features):
    folds, individual_predictions, team_predictions = [], [], []
    for test_season in SEASONS[1:]:
        split = SEASONS.index(test_season)
        train = features[features["season"].isin(SEASONS[:split])].copy()
        test = features[features["season"] == test_season].copy()
        model = _model()
        model.fit(train[PLAYER_FEATURES], train["player_a_win"])
        test["player_a_probability"] = model.predict_proba(test[PLAYER_FEATURES])[:, 1]
        test["player_elo_probability"] = test.apply(
            lambda row: elo_probability(row["player_a_elo"], row["player_b_elo"]), axis=1
        )
        test["home_probability"] = np.where(
            test["home_player_id"] == test["player_a_id"],
            test["player_a_probability"], 1 - test["player_a_probability"],
        )
        test["home_elo_probability"] = np.where(
            test["home_player_id"] == test["player_a_id"],
            test["player_elo_probability"], 1 - test["player_elo_probability"],
        )
        individual_predictions.append(test)
        complete = test.groupby("source_match_id").filter(lambda group: len(group) == 9)
        team = complete.groupby("source_match_id").agg(
            season=("season", "first"),
            actual_home_won=("home_probability", lambda values: np.nan),
            lineup_probability=("home_probability", lambda values: probability_at_least_five(values)),
            player_elo_probability=("home_elo_probability", lambda values: probability_at_least_five(values)),
        ).reset_index()
        actual = complete.groupby("source_match_id").apply(
            lambda group: int(sum(
                ((group["player_a_win"] == 1) & (group["home_player_id"] == group["player_a_id"])) |
                ((group["player_a_win"] == 0) & (group["home_player_id"] != group["player_a_id"]))
            ) >= 5), include_groups=False
        )
        team["actual_home_won"] = team["source_match_id"].map(actual)
        team_predictions.append(team)
        folds.append({
            "test_season": test_season, "training_individual_matches": len(train),
            "test_individual_matches": len(test), "test_team_matches": len(team),
            "individual_metrics": metrics(test["player_a_win"], test["player_a_probability"]),
            "individual_elo_metrics": metrics(
                test["player_a_win"], test["player_elo_probability"]
            ),
            "lineup_team_metrics": metrics(team["actual_home_won"], team["lineup_probability"]),
            "player_elo_team_metrics": metrics(team["actual_home_won"], team["player_elo_probability"]),
            "coefficients": dict(zip(
                PLAYER_FEATURES, model.named_steps["logisticregression"].coef_[0]
            )),
        })
    individuals = pd.concat(individual_predictions, ignore_index=True)
    teams = pd.concat(team_predictions, ignore_index=True)
    return {
        "folds": folds, "individual_predictions": individuals, "team_predictions": teams,
        "aggregate": {
            "individual": metrics(individuals["player_a_win"], individuals["player_a_probability"]),
            "individual_elo": metrics(
                individuals["player_a_win"], individuals["player_elo_probability"]
            ),
            "lineup_team": metrics(teams["actual_home_won"], teams["lineup_probability"]),
            "player_elo_team": metrics(teams["actual_home_won"], teams["player_elo_probability"]),
        },
    }


def official_rating_walk_forward(features):
    """Compare rating, Elo, combined, and prior full models on rated matches only."""
    folds, individual_predictions, team_predictions = [], [], []
    for test_season in SEASONS[1:]:
        split = SEASONS.index(test_season)
        train_all = features[features["season"].isin(SEASONS[:split])].copy()
        test = features[
            (features["season"] == test_season) & features["official_rating_diff"].notna()
        ].copy()
        train_rated = train_all[train_all["official_rating_diff"].notna()].copy()
        if train_rated.empty or test.empty:
            continue
        models = {
            "official_rating": (_model(), OFFICIAL_RATING_FEATURES, train_rated),
            "official_and_elo": (_model(), OFFICIAL_AND_ELO_FEATURES, train_rated),
            "previous_full": (_model(), PLAYER_FEATURES, train_all),
        }
        test["player_elo_probability"] = test.apply(
            lambda row: elo_probability(row["player_a_elo"], row["player_b_elo"]), axis=1
        )
        probabilities = {"player_elo": test["player_elo_probability"]}
        coefficients = {}
        for name, (model, columns, train) in models.items():
            model.fit(train[columns], train["player_a_win"])
            probabilities[name] = pd.Series(
                model.predict_proba(test[columns])[:, 1], index=test.index
            )
            coefficients[name] = dict(zip(
                columns, model.named_steps["logisticregression"].coef_[0].astype(float)
            ))
        for name, values in probabilities.items():
            test[f"{name}_probability"] = values
            test[f"{name}_home_probability"] = np.where(
                test["home_player_id"] == test["player_a_id"], values, 1 - values
            )
        individual_predictions.append(test)

        complete = test.groupby("source_match_id").filter(lambda group: len(group) == 9)
        team_rows = []
        for source_match_id, group in complete.groupby("source_match_id"):
            home_wins = sum(
                ((group["player_a_win"] == 1) & (group["home_player_id"] == group["player_a_id"])) |
                ((group["player_a_win"] == 0) & (group["home_player_id"] != group["player_a_id"]))
            )
            row = {
                "source_match_id": source_match_id, "season": test_season,
                "actual_home_won": int(home_wins >= 5),
            }
            for name in probabilities:
                position_probabilities = group[f"{name}_home_probability"].tolist()
                distribution = lineup_score_distribution(position_probabilities)
                row[f"{name}_lineup_probability"] = min(
                    1.0, max(0.0, float(distribution[5:].sum()))
                )
                row[f"{name}_expected_home_wins"] = expected_individual_wins(
                    position_probabilities
                )
                row[f"{name}_score_distribution"] = json.dumps(
                    [float(value) for value in distribution]
                )
            team_rows.append(row)
        teams = pd.DataFrame(team_rows)
        team_predictions.append(teams)
        fold = {
            "test_season": test_season, "training_rated_matches": len(train_rated),
            "test_rated_matches": len(test), "complete_rated_lineups": len(teams),
            "coefficients": coefficients,
        }
        for name, values in probabilities.items():
            fold[f"{name}_individual_metrics"] = metrics(test["player_a_win"], values)
            if not teams.empty:
                fold[f"{name}_lineup_metrics"] = metrics(
                    teams["actual_home_won"], teams[f"{name}_lineup_probability"]
                )
        folds.append(fold)
    individuals = pd.concat(individual_predictions, ignore_index=True)
    teams = pd.concat(team_predictions, ignore_index=True)
    model_names = ["player_elo", "official_rating", "official_and_elo", "previous_full"]
    aggregate = {"individual": {}, "lineup": {}}
    for name in model_names:
        aggregate["individual"][name] = metrics(
            individuals["player_a_win"], individuals[f"{name}_probability"]
        )
        aggregate["lineup"][name] = metrics(
            teams["actual_home_won"], teams[f"{name}_lineup_probability"]
        )
    return {
        "folds": folds, "aggregate": aggregate,
        "individual_predictions": individuals, "team_predictions": teams,
    }

from itertools import combinations
import math
from pathlib import Path

import joblib
import pytest

from college_squash.database import connect_database
from college_squash.player_modeling import probability_at_least_five
from college_squash.preseason import predict_preseason_matchup


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def independent_probability(probabilities):
    return sum(
        math.prod(
            probability if index in winners else 1 - probability
            for index, probability in enumerate(probabilities)
        )
        for count in range(5, 10)
        for winners in map(set, combinations(range(9), count))
    )


def test_rochester_mit_probability_inputs_and_orientation():
    artifact = joblib.load(PROJECT_ROOT / "data/preseason_player_model.joblib")
    with connect_database(PROJECT_ROOT / "data/college_squash.db") as connection:
        rochester = predict_preseason_matchup(
            connection, artifact, "University of Rochester", "MIT", "men"
        )
        mit = predict_preseason_matchup(
            connection, artifact, "MIT", "University of Rochester", "men"
        )

    probabilities = rochester["pairings"]["team_one_probability"].tolist()
    reverse = mit["pairings"]["team_one_probability"].tolist()
    exact = probability_at_least_five(probabilities)

    assert rochester["team_one_expected_wins"] == pytest.approx(sum(probabilities))
    assert rochester["team_one_probability"] == pytest.approx(exact)
    assert exact == pytest.approx(independent_probability(probabilities))
    assert exact == pytest.approx(0.0032116811918152595)
    assert mit["team_one_probability"] == pytest.approx(1 - exact)
    assert all(first + second == pytest.approx(1.0)
               for first, second in zip(probabilities, reverse))

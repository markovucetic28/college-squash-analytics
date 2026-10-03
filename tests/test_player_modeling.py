import sqlite3
from itertools import combinations
import math
import pytest

from college_squash.player_modeling import (
    build_player_feature_dataset, expected_individual_wins, lineup_score_distribution,
    probability_at_least_five,
)


def test_exact_five_of_nine_probability():
    assert probability_at_least_five([0.5] * 9) == pytest.approx(0.5)
    assert probability_at_least_five([1] * 5 + [0] * 4) == pytest.approx(1.0)
    assert probability_at_least_five([1] * 4 + [0] * 5) == pytest.approx(0.0)
    distribution = lineup_score_distribution([0.5] * 9)
    assert sum(distribution) == pytest.approx(1.0)
    assert expected_individual_wins([0.6] * 9) == pytest.approx(5.4)


def test_lineup_requires_nine_valid_probabilities():
    with pytest.raises(ValueError, match="nine"):
        probability_at_least_five([0.5] * 8)
    with pytest.raises(ValueError, match="between"):
        probability_at_least_five([0.5] * 8 + [1.1])


def _independent_at_least_five(probabilities):
    total = 0.0
    positions = range(9)
    for win_count in range(5, 10):
        for winners in combinations(positions, win_count):
            winner_set = set(winners)
            total += math.prod(
                probability if index in winner_set else 1 - probability
                for index, probability in enumerate(probabilities)
            )
    return total


@pytest.mark.parametrize("probabilities", [
    [0.5] * 9,
    [0.8] * 9,
    [0.12, 0.27, 0.41, 0.49, 0.53, 0.61, 0.72, 0.84, 0.93],
])
def test_exact_team_probability_matches_independent_enumeration(probabilities):
    exact = probability_at_least_five(probabilities)

    assert expected_individual_wins(probabilities) == pytest.approx(sum(probabilities))
    assert exact == pytest.approx(_independent_at_least_five(probabilities))
    assert 0 <= exact <= 1
    assert probability_at_least_five([1 - value for value in probabilities]) == pytest.approx(
        1 - exact
    )


def test_same_day_matches_do_not_update_each_others_features():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE divisions (division_id INTEGER, gender TEXT);
        CREATE TABLE matches (source_match_id INTEGER, division_id INTEGER,
                              match_date TEXT, season TEXT);
        CREATE TABLE individual_matches (
            individual_match_id INTEGER, source_match_id INTEGER, position INTEGER,
            home_player_id INTEGER, away_player_id INTEGER, winner_side TEXT
        );
        INSERT INTO divisions VALUES (1, 'men');
        INSERT INTO matches VALUES (1, 1, '2019-11-01', '2019-20');
        INSERT INTO matches VALUES (2, 1, '2019-11-01', '2019-20');
        INSERT INTO matches VALUES (3, 1, '2019-11-02', '2019-20');
        INSERT INTO individual_matches VALUES (1, 1, 1, 10, 20, 'H');
        INSERT INTO individual_matches VALUES (2, 2, 1, 10, 30, 'H');
        INSERT INTO individual_matches VALUES (3, 3, 1, 10, 40, 'H');
    """)
    features = build_player_feature_dataset(connection)
    assert features.loc[0, "player_a_elo"] == 1500
    assert features.loc[1, "player_a_elo"] == 1500
    assert features.loc[2, "player_a_elo"] > 1500


def test_future_season_cannot_change_earlier_features():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE divisions (division_id INTEGER, gender TEXT);
        CREATE TABLE matches (source_match_id INTEGER, division_id INTEGER,
                              match_date TEXT, season TEXT);
        CREATE TABLE individual_matches (
            individual_match_id INTEGER, source_match_id INTEGER, position INTEGER,
            home_player_id INTEGER, away_player_id INTEGER, winner_side TEXT
        );
        INSERT INTO divisions VALUES (1, 'women');
        INSERT INTO matches VALUES (1, 1, '2019-11-01', '2019-20');
        INSERT INTO matches VALUES (2, 1, '2021-11-01', '2021-22');
        INSERT INTO individual_matches VALUES (1, 1, 1, 10, 20, 'H');
        INSERT INTO individual_matches VALUES (2, 2, 1, 10, 20, 'V');
    """)
    before = build_player_feature_dataset(connection).iloc[0].to_dict()
    connection.execute("UPDATE individual_matches SET winner_side='H' WHERE individual_match_id=2")
    after = build_player_feature_dataset(connection).iloc[0].to_dict()
    assert before == after

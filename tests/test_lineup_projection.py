import pandas as pd

from college_squash.lineup_projection import (
    build_historical_projections, lineup_agreement, lineup_confidence,
    most_recent_lineup, rating_before, rating_lookup, recent_consensus_lineup,
)


def test_recent_and_consensus_lineups_use_only_observed_players():
    first = list(range(1, 10))
    second = [1, 2, 3, 4, 5, 6, 7, 10, 9]
    assert most_recent_lineup([first, second]) == second
    consensus = recent_consensus_lineup([first, second])
    assert len(consensus) == 9
    assert set(consensus) <= set(first + second)


def test_same_day_lineups_cannot_influence_each_other():
    rows = []
    for match_id in (1, 2):
        for position in range(1, 10):
            rows.append({
                "source_match_id": match_id, "match_date": "2024-01-01", "side": "home",
                "program_id": 1, "season": "2023-24", "position": position,
                "player_id": match_id * 100 + position,
            })
    projected = build_historical_projections(pd.DataFrame(rows))
    recent = projected[projected["method"] == "most_recent"]
    assert recent["projected_lineup"].isna().all()


def test_lineup_agreement_and_confidence_are_bounded():
    actual = list(range(1, 10))
    projected = [1, 2, 3, 4, 5, 6, 7, 9, 10]
    result = lineup_agreement(projected, actual)
    assert result == {"correct_players": 8, "correct_positions": 7, "all_players_correct": False}
    assert 0 <= lineup_confidence([actual, projected], projected) <= 1
    assert lineup_confidence([actual], actual) <= 1 / 3


def test_prior_season_lineup_is_not_used_as_current_season_availability():
    rows = []
    for match_id, date, season in [
        (1, "2023-02-01", "2022-23"), (2, "2023-11-01", "2023-24")
    ]:
        for position in range(1, 10):
            rows.append({
                "source_match_id": match_id, "match_date": date, "season": season,
                "side": "home", "program_id": 1, "position": position,
                "player_id": match_id * 100 + position,
            })
    projected = build_historical_projections(pd.DataFrame(rows))
    later = projected[
        (projected["source_match_id"] == 2) & (projected["method"] == "most_recent")
    ].iloc[0]
    assert later["projected_lineup"] is None


def test_rating_lookup_is_strictly_before_match_date():
    ratings = pd.DataFrame({
        "player_id": [1, 1], "rating_date": ["2024-01-01", "2024-01-08"],
        "rating": [5.0, 5.2],
    })
    lookup = rating_lookup(ratings)
    assert rating_before(lookup, 1, "2024-01-08") == 5.0
    assert rating_before(lookup, 1, "2024-01-09") == 5.2

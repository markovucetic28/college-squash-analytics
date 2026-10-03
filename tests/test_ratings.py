import pandas as pd

from college_squash.ratings import (
    latest_rating_strictly_before, match_historical_ratings, parse_rating_history,
)


def ratings():
    return pd.DataFrame({
        "player_id": [1, 1, 1, 2],
        "rating_date": pd.to_datetime(["2023-09-01", "2023-10-01", "2024-09-01", "2023-09-15"]),
        "rating": [5.0, 5.2, 5.8, 4.7],
    })


def test_latest_rating_is_strictly_before_match_date():
    selected = latest_rating_strictly_before(ratings(), 1, "2023-10-01")
    assert selected["rating"] == 5.0
    assert selected["rating_date"] == pd.Timestamp("2023-09-01")


def test_future_seasons_cannot_leak_backward():
    selected = latest_rating_strictly_before(ratings(), 1, "2023-11-01")
    assert selected["rating"] == 5.2
    assert selected["rating"] != 5.8


def test_match_rating_mapping_keeps_stable_player_ids_and_ages():
    matches = pd.DataFrame([{
        "individual_match_id": 10, "match_date": "2023-10-01",
        "home_player_id": 1, "away_player_id": 2,
    }])
    result = match_historical_ratings(matches, ratings()).iloc[0]
    assert result["home_rating"] == 5.0
    assert result["away_rating"] == 4.7
    assert result["home_rating_age_days"] == 30
    assert result["away_rating_age_days"] == 16


def test_parser_rejects_non_universal_and_preserves_provenance():
    frame = parse_rating_history([
        {"RankingPeriod": "2023-09-30", "NewRating": 5.1,
         "RankingGroupId": 208, "RatingGroupDescr": "Universal Squash Rating",
         "DivisionID": 0, "Season": "2023-2024"},
        {"RankingPeriod": "2023-09-30", "NewRating": 99,
         "RankingGroupId": 99, "RatingGroupDescr": "Other"},
    ], 7, "2026-10-02T00:00:00Z")
    assert len(frame) == 1
    assert frame.iloc[0]["player_id"] == 7
    assert "/user/7/rankings?history=yes" in frame.iloc[0]["source_url"]


def test_parser_prefers_universal_snapshot_over_duplicate_rankings():
    frame = parse_rating_history([
        {"RankingPeriod": "2024-01-03", "NewRating": 5.21,
         "RankingGroupId": 1, "RatingGroupDescr": "US SQUASH",
         "DivisionID": 2, "Season": "2023-2024"},
        {"RankingPeriod": "2024-01-03", "NewRating": 5.23,
         "RankingGroupId": 208, "RatingGroupDescr": "Universal Squash Rating",
         "DivisionID": 0, "Season": "2023-2024"},
    ], 7, "2026-10-02T00:00:00Z")
    assert len(frame) == 1
    assert frame.iloc[0]["rating"] == 5.23
    assert frame.iloc[0]["ranking_group_id"] == 208

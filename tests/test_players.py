import json

import pytest

from college_squash.players import parse_scorecard_rows, position_number, roster_identities


def scorecard_rows(home_wins=5):
    rows = []
    for position in range(1, 10):
        winner = "H" if position <= home_wins else "V"
        rows.append({
            "positionPlayed": f"{position}S", "status": "C", "winner": winner,
            "id": 100 + position, "wid1": 1000 + position,
            "oid1": 2000 + position, "wset1": 11, "oset1": 5,
            "wset2": 11, "oset2": 7, "wset3": 11, "oset3": 8,
            "wset4": 0, "oset4": 0, "wset5": 0, "oset5": 0,
        })
    rows.append({"positionPlayed": "10S"})
    return rows


def test_position_mapping_only_accepts_official_lineup():
    assert position_number("1S") == 1
    assert position_number("9S") == 9
    assert position_number("10S") is None
    assert position_number("1D") is None


def test_scorecard_reproduces_team_score_and_maps_home_player():
    match = {"source_match_id": 12, "home_score": 5, "away_score": 4}
    parsed = parse_scorecard_rows(scorecard_rows(), match)
    assert len(parsed) == 9
    assert parsed[0]["home_player_id"] == 1001
    assert parsed[-1]["away_player_id"] == 1009
    assert json.loads(parsed[0]["game_scores_winner_first"])[0] == [11, 5]


def test_scorecard_rejects_score_mismatch():
    match = {"source_match_id": 12, "home_score": 6, "away_score": 3}
    with pytest.raises(ValueError, match="does not match"):
        parse_scorecard_rows(scorecard_rows(), match)


def test_roster_uses_official_id_and_ignores_current_rating():
    identities, memberships = roster_identities(
        [{"playerid": 7, "player": " Smith,  Jane ", "CurrentRating": 6.2,
          "TeamPosition": "2"}], 10, 20
    )
    assert identities == [{"player_id": 7, "display_name": "Smith, Jane"}]
    assert "CurrentRating" not in memberships[0]

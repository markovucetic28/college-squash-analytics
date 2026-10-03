from pathlib import Path
import sys

from fastapi.testclient import TestClient
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from college_squash.api import app

client = TestClient(app)


def matchup():
    teams = client.get("/api/teams", params={"gender": "men"}).json()
    first = next(team for team in teams if team["name"] == "Harvard University")
    second = next(team for team in teams if team["name"] == "Yale University")
    original = client.get("/api/compare", params={
        "team_one_id": first["program_id"], "team_two_id": second["program_id"],
    }).json()["projection"]
    first_roster = client.get(f"/api/teams/{first['program_id']}").json()["roster"]
    second_roster = client.get(f"/api/teams/{second['program_id']}").json()["roster"]
    return first, second, original, first_roster, second_roster


def payload(first, second, original):
    return {
        "team_one_id": first["program_id"], "team_two_id": second["program_id"],
        "team_one_lineup": [row["team_one_player_id"] for row in original["pairings"]],
        "team_two_lineup": [row["team_two_player_id"] for row in original["pairings"]],
    }


def test_reorder_and_replacement_recalculate_without_changing_stored_projection():
    first, second, original, first_roster, _ = matchup()
    request = payload(first, second, original)
    request["team_one_lineup"][1], request["team_one_lineup"][3] = (
        request["team_one_lineup"][3], request["team_one_lineup"][1]
    )
    used = set(request["team_one_lineup"])
    substitute = next(player["player_id"] for player in first_roster
                      if player["player_id"] not in used and player["current_rating"] is not None)
    request["team_one_lineup"][-1] = substitute
    response = client.post("/api/compare/custom-lineup", json=request)
    assert response.status_code == 200
    custom = response.json()
    assert custom["mode"] == "custom"
    assert custom["pairings"][1]["team_one_player_id"] == request["team_one_lineup"][1]
    assert custom["pairings"][-1]["team_one_player_id"] == substitute
    assert custom["team_one_probability"] != original["team_one_probability"]
    assert len(custom["team_one_score_distribution"]) == 10
    assert sum(custom["team_one_score_distribution"]) == pytest.approx(1)
    unchanged = client.get("/api/compare", params={
        "team_one_id": first["program_id"], "team_two_id": second["program_id"],
    }).json()["projection"]
    assert unchanged["pairings"] == original["pairings"]


@pytest.mark.parametrize("players", [8, 7])
def test_legal_short_custom_lineups_use_deterministic_forfeits(players):
    first, second, original, _, _ = matchup()
    request = payload(first, second, original)
    request["team_one_lineup"] = request["team_one_lineup"][:players] + [None] * (9-players)
    projection = client.post("/api/compare/custom-lineup", json=request).json()
    assert sum(row["team_one_is_forfeit"] for row in projection["pairings"]) == 9-players
    assert all(row["team_one_probability"] == 0 for row in projection["pairings"][players:])


def test_duplicate_wrong_team_and_malformed_forfeits_are_rejected():
    first, second, original, _, _ = matchup()
    request = payload(first, second, original)
    request["team_one_lineup"][1] = request["team_one_lineup"][0]
    assert client.post("/api/compare/custom-lineup", json=request).status_code == 422

    request = payload(first, second, original)
    request["team_one_lineup"][0] = request["team_two_lineup"][0]
    assert client.post("/api/compare/custom-lineup", json=request).status_code == 422

    request = payload(first, second, original)
    request["team_one_lineup"] = request["team_one_lineup"] + [None]
    assert client.post("/api/compare/custom-lineup", json=request).status_code == 422

    request = payload(first, second, original)
    request["team_one_lineup"][4] = None
    assert client.post("/api/compare/custom-lineup", json=request).status_code == 422


def test_swapping_custom_team_orientation_is_exactly_complementary():
    first, second, original, _, _ = matchup()
    request = payload(first, second, original)
    forward = client.post("/api/compare/custom-lineup", json=request).json()
    reverse = client.post("/api/compare/custom-lineup", json={
        "team_one_id": second["program_id"], "team_two_id": first["program_id"],
        "team_one_lineup": request["team_two_lineup"],
        "team_two_lineup": request["team_one_lineup"],
    }).json()
    assert forward["team_one_probability"] + reverse["team_one_probability"] == pytest.approx(1)
    assert all(
        left["team_one_probability"] + right["team_one_probability"] == pytest.approx(1)
        for left, right in zip(forward["pairings"], reverse["pairings"])
    )

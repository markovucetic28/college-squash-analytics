from pathlib import Path
import sys

from fastapi.testclient import TestClient
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import college_squash.api as api_module
from college_squash.api import app, clear_schedule_prediction_cache, cors_origins


client = TestClient(app)


def test_cors_origins_use_explicit_environment(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://squash.example, https://www.squash.example")
    assert cors_origins() == ["https://squash.example", "https://www.squash.example"]


def test_cors_preflight_allows_custom_lineup_post():
    response = client.options("/api/compare/custom-lineup", headers={
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "POST",
    })
    assert response.status_code == 200
    assert "POST" in response.headers["access-control-allow-methods"]


def test_schedule_returns_all_validated_current_fixtures():
    response = client.get("/api/schedule", params={"limit": 500})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 426
    assert len(payload["items"]) == 426
    assert all(match["season"] == "2026-27" for match in payload["items"])
    assert all(isinstance(match["projection_available"], bool) for match in payload["items"])


def test_status_exposes_refresh_and_frozen_model_metadata():
    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.json()["current_season"] == "2026-27"
    assert response.json()["model"]["frozen"] is True


def test_normalized_player_search_and_empty_query():
    response = client.get("/api/players/search", params={"q": "char raven"})

    assert response.status_code == 200
    assert any(player["name"] == "Charlie Raven" for player in response.json())
    assert client.get("/api/players/search", params={"q": ""}).json() == []


def test_team_detail_contains_current_roster_only():
    teams = client.get("/api/teams", params={"gender": "men"}).json()
    harvard = next(team for team in teams if team["name"] == "Harvard University")
    response = client.get(f"/api/teams/{harvard['program_id']}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Harvard University"
    assert payload["roster"]
    assert all(player["rating_date"] and player["player_id"] for player in payload["roster"])
    assert all(player["recent_form"]["state"] in {"above", "expected", "below", "limited"}
               for player in payload["roster"])


def test_player_profile_supports_current_only_newcomers():
    teams = client.get("/api/teams", params={"gender": "men"}).json()
    profiles = []
    for team in teams:
        detail = client.get(f"/api/teams/{team['program_id']}").json()
        profiles.extend(detail["roster"])
        if any(player["career_matches"] == 0 for player in detail["roster"]):
            break
    newcomer = next(player for player in profiles if player["career_matches"] == 0)

    response = client.get(f"/api/players/{newcomer['player_id']}")
    assert response.status_code == 200
    assert response.json()["verified_record"]["matches"] == 0


def test_player_match_history_has_link_targets_and_readable_scores():
    player = client.get("/api/players/83429").json()

    assert player["latest_membership"]["program_id"]
    assert player["matches"]
    for match in player["matches"]:
        assert match["opponent_player_id"]
        assert match["opponent_team_id"]
        assert match["opponent_team"]
        assert "[[" not in match["formatted_score"]
        assert "–" in match["formatted_score"]


def test_match_detail_has_bounded_player_prediction_and_current_roster_players():
    schedule = client.get("/api/schedule", params={"limit": 500}).json()["items"]
    teams = client.get("/api/teams").json()
    current_names = {(team["name"], team["gender"]) for team in teams}
    fixture = next(match for match in schedule
                   if (match["away_team"], match["gender"]) in current_names
                   and (match["home_team"], match["gender"]) in current_names)

    response = client.get(f"/api/matches/{fixture['source_match_id']}")
    assert response.status_code == 200
    projection = response.json()["projection"]
    assert projection["available"]
    assert 0 <= projection["team_one_probability"] <= 1
    assert 0 <= projection["team_two_probability"] <= 1
    assert len(projection["pairings"]) == 9
    assert all(pairing["team_one_recent_form"]["label"]
               and pairing["team_two_recent_form"]["label"]
               for pairing in projection["pairings"])

    first_id = next(team["program_id"] for team in teams
                    if team["name"] == fixture["away_team"] and team["gender"] == fixture["gender"])
    second_id = next(team["program_id"] for team in teams
                     if team["name"] == fixture["home_team"] and team["gender"] == fixture["gender"])
    roster_ids = {
        player["player_id"]
        for team_id in (first_id, second_id)
        for player in client.get(f"/api/teams/{team_id}").json()["roster"]
    }
    projected_ids = {
        player_id for pairing in projection["pairings"]
        for player_id in (pairing["team_one_player_id"], pairing["team_two_player_id"])
    }
    assert projected_ids <= roster_ids


def test_rankings_compare_and_methodology_routes():
    teams = client.get("/api/teams", params={"gender": "women"}).json()
    rankings = client.get("/api/rankings", params={
        "gender": "women", "season": "2025-26"
    })
    comparison = client.get("/api/compare", params={
        "team_one_id": teams[0]["program_id"], "team_two_id": teams[1]["program_id"]
    })

    assert rankings.status_code == 200 and rankings.json()["items"]
    assert comparison.status_code == 200
    assert client.get("/api/methodology/summary").status_code == 200


def test_compare_preserves_team_a_orientation_when_teams_are_reversed():
    rochester = client.get("/api/compare", params={
        "team_one_id": 95, "team_two_id": 59,
    }).json()
    mit = client.get("/api/compare", params={
        "team_one_id": 59, "team_two_id": 95,
    }).json()

    assert rochester["team_one"]["name"] == "University of Rochester"
    assert rochester["team_two"]["name"] == "MIT"
    assert mit["team_one"]["name"] == "MIT"
    assert mit["team_two"]["name"] == "University of Rochester"
    assert rochester["projection"]["team_one_probability"] + mit["projection"]["team_one_probability"] == pytest.approx(1)
    assert all(
        first["team_one_probability"] + second["team_one_probability"] == pytest.approx(1)
        for first, second in zip(
            rochester["projection"]["pairings"],
            mit["projection"]["pairings"],
        )
    )


def test_fordham_st_lawrence_projection_reconstructs_exactly():
    projection = client.get("/api/matches/253544").json()["projection"]
    first = projection["pairings"][0]
    assert first["team_one_player"] == "Cukierman, Nathan"
    assert first["team_two_player"] == "Yousef, Mina"
    assert first["team_one_rating"] == pytest.approx(6.195701)
    assert first["team_two_rating"] == pytest.approx(6.322927)
    assert first["team_one_probability"] == pytest.approx(0.2985532711908701)
    assert projection["team_one_probability"] == pytest.approx(0.18783951715954283)
    assert projection["team_one_probability"] + projection["team_two_probability"] == pytest.approx(1)
    assert sum(projection["team_one_score_distribution"]) == pytest.approx(1)


def test_schedule_prediction_batch_is_cached_and_timestamp_invalidates(monkeypatch):
    clear_schedule_prediction_cache()
    calls = []
    monkeypatch.setattr(api_module, "current_data_timestamp", lambda: "first")
    monkeypatch.setattr(api_module, "projection_payload", lambda *args: (
        calls.append(1) or {"team_one_probability": .6, "team_two_probability": .4,
                            "mode": "preseason", "mode_label": "Preseason projection"}
    ))
    request = {"match_ids": [253544]}
    assert client.post("/api/schedule/predictions", json=request).status_code == 200
    assert client.post("/api/schedule/predictions", json=request).status_code == 200
    assert len(calls) == 1
    monkeypatch.setattr(api_module, "current_data_timestamp", lambda: "second")
    assert client.post("/api/schedule/predictions", json=request).status_code == 200
    assert len(calls) == 2
    clear_schedule_prediction_cache()

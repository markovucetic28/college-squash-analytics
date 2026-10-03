import json
import re
import time
from pathlib import Path

import pandas as pd
import requests


API_ROOT = "https://api.ussquash.com/resources"
USER_AGENT = "CollegeSquashAnalytics/1.0 (university research project)"
OFFICIAL_POSITIONS = set(range(1, 10))


def position_number(value):
    match = re.fullmatch(r"([1-9])S", str(value or "").strip())
    return int(match.group(1)) if match else None


def parse_scorecard_rows(rows, team_match):
    """Return the nine official individual matches; reserve positions are excluded."""
    source_match_id = int(team_match.get("source_match_id", team_match.get("source_id")))
    parsed = []
    for row in rows:
        position = position_number(row.get("positionPlayed"))
        if position not in OFFICIAL_POSITIONS:
            continue
        winner_side = row.get("winner")
        if row.get("status") != "C" or winner_side not in {"H", "V"}:
            raise ValueError(f"Incomplete result at position {position}")
        winner_id, loser_id = int(row.get("wid1", 0)), int(row.get("oid1", 0))
        if winner_id <= 0 or loser_id <= 0:
            raise ValueError(f"Missing player identity at position {position}")
        home_player_id, away_player_id = (
            (winner_id, loser_id) if winner_side == "H" else (loser_id, winner_id)
        )
        games = []
        for number in range(1, 6):
            winner_score = int(row.get(f"wset{number}") or 0)
            loser_score = int(row.get(f"oset{number}") or 0)
            if winner_score or loser_score:
                games.append([winner_score, loser_score])
        parsed.append({
            "individual_match_id": int(row["id"]),
            "source_match_id": source_match_id,
            "position": position,
            "home_player_id": home_player_id,
            "away_player_id": away_player_id,
            "winner_side": winner_side,
            "winner_player_id": winner_id,
            "loser_player_id": loser_id,
            "game_scores_winner_first": json.dumps(games),
            "source_url": f"{API_ROOT}/leagues/scorecards/{source_match_id}/list",
        })
    positions = [row["position"] for row in parsed]
    if len(parsed) != 9 or len(set(positions)) != 9:
        raise ValueError(f"Expected positions 1-9 exactly once; found {sorted(positions)}")
    home_wins = sum(row["winner_side"] == "H" for row in parsed)
    away_wins = 9 - home_wins
    if (home_wins, away_wins) != (team_match["home_score"], team_match["away_score"]):
        raise ValueError(
            f"Lineup score {home_wins}-{away_wins} does not match team score "
            f"{team_match['home_score']}-{team_match['away_score']}"
        )
    return parsed


def normalize_player_name(name):
    return " ".join(str(name or "").strip().split()) or None


def roster_identities(rows, division_id, team_id):
    identities, memberships = [], []
    for row in rows:
        player_id = int(row.get("playerid") or 0)
        if player_id <= 0:
            continue
        name = normalize_player_name(row.get("player"))
        identities.append({"player_id": player_id, "display_name": name})
        memberships.append({
            "player_id": player_id,
            "division_id": int(division_id),
            "team_id": int(team_id),
            "roster_position": row.get("TeamPosition"),
            "source_url": f"{API_ROOT}/teams/{team_id}/players",
        })
    return identities, memberships


def download_json(url, output_path, session=None, delay=0.25, retries=3):
    """Download one public JSON resource, preserving it as an untouched snapshot."""
    output_path = Path(output_path)
    if output_path.exists():
        return json.loads(output_path.read_text(encoding="utf-8"))
    session = session or requests.Session()
    for attempt in range(retries):
        try:
            response = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
            response.raise_for_status()
            data = response.json()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            time.sleep(delay)
            return data
        except (requests.RequestException, ValueError):
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)


def load_player_dataset(raw_directory, matches):
    raw_directory = Path(raw_directory)
    individual_rows, exclusions = [], []
    for match in matches.to_dict("records"):
        source_match_id = int(match.get("source_match_id", match.get("source_id")))
        path = raw_directory / "player_scorecards" / f"{source_match_id}.json"
        if not path.exists():
            exclusions.append({"source_match_id": source_match_id, "reason": "snapshot_missing"})
            continue
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
            individual_rows.extend(parse_scorecard_rows(rows, match))
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
            exclusions.append({"source_match_id": source_match_id, "reason": str(error)})
    return pd.DataFrame(individual_rows), pd.DataFrame(exclusions)

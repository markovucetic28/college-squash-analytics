import json
from pathlib import Path

import pandas as pd

from college_squash.clublocker import normalize_team_name


CURRENT_SEASON = "2026-27"
CURRENT_DIVISIONS = {"men": 6376, "women": 6379}


def load_current_schedule(raw_directory):
    """Load scheduled fixtures separately from completed historical results."""
    raw_directory = Path(raw_directory) / f"current_{CURRENT_SEASON}"
    scheduled, exclusions = [], []
    for gender, division_id in CURRENT_DIVISIONS.items():
        path = raw_directory / f"csa_{gender}_varsity_{CURRENT_SEASON}.json"
        if not path.exists():
            continue
        teams_path = raw_directory / f"csa_{gender}_varsity_{CURRENT_SEASON}_teams.json"
        varsity_ids = set()
        if teams_path.exists():
            varsity_ids = {
                int(row["teamid"])
                for row in json.loads(teams_path.read_text())
                if row.get("teamid") is not None
            }
        metadata_path = raw_directory / f"csa_{gender}_varsity_{CURRENT_SEASON}.metadata.json"
        metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
        for row in json.loads(path.read_text()):
            if row.get("Score_Entered") == "Confirmed":
                continue
            source_id = row.get("scorecardid")
            required = [source_id, row.get("matchdate"), row.get("wTeamName"),
                        row.get("oTeamName"), row.get("hteamid"), row.get("vteamid")]
            if any(value is None or value == "" for value in required):
                exclusions.append({
                    "source_match_id": source_id, "gender": gender,
                    "reason": "scheduled match is malformed",
                })
                continue
            home_id, away_id = int(row["hteamid"]), int(row["vteamid"])
            if varsity_ids and home_id not in varsity_ids and away_id not in varsity_ids:
                exclusions.append({
                    "source_match_id": source_id, "gender": gender,
                    "reason": "neither team is in the official varsity division standings",
                })
                continue
            match_date = pd.to_datetime(row["matchdate"], format="%m/%d/%y", errors="coerce")
            if pd.isna(match_date):
                exclusions.append({
                    "source_match_id": source_id, "gender": gender,
                    "reason": "scheduled match date is malformed",
                })
                continue
            scheduled.append({
                "source_match_id": int(source_id), "season": CURRENT_SEASON,
                "gender": gender, "division_id": division_id,
                "match_date": match_date.strftime("%Y-%m-%d"),
                "match_time": (row.get("MatchTime") or "").strip() or None,
                "home_team_id": home_id,
                "home_team": normalize_team_name(row["wTeamName"]),
                "away_team_id": away_id,
                "away_team": normalize_team_name(row["oTeamName"]),
                "venue_name": (row.get("VenueName") or "").strip() or None,
                "status": row.get("Score_Entered") or "Scheduled",
                "source_url": f"https://clublocker.com/divisions/{division_id}/matches",
                "source_data_url": (
                    f"https://api.ussquash.com/resources/divisions/schedule/{division_id}/"
                ),
                "retrieved_at_utc": metadata.get("retrieved_at_utc"),
            })
    frame = pd.DataFrame(scheduled)
    if not frame.empty and frame["source_match_id"].duplicated().any():
        raise ValueError("Duplicate current-season schedule IDs")
    return frame, pd.DataFrame(exclusions)

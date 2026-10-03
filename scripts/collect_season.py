from datetime import datetime, timezone
from pathlib import Path
import json
import sys
import time

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from college_squash.clublocker import (
    SEASONS, USER_AGENT, normalize_team_name, results_page_url,
    schedule_api_url, standings_api_url,
)


def collect_season(season):
    if season not in SEASONS:
        raise ValueError(f"Unknown season: {season}")
    raw_directory = PROJECT_ROOT / "data/raw"
    retrieved_at = datetime.now(timezone.utc).isoformat()
    for gender, division_id in SEASONS[season].items():
        schedule_response = requests.get(
            schedule_api_url(division_id), headers={"User-Agent": USER_AGENT}, timeout=60
        )
        schedule_response.raise_for_status()
        schedule = schedule_response.json()
        stem = f"csa_{gender}_varsity_{season}"
        (raw_directory / f"{stem}.json").write_text(
            json.dumps(schedule, indent=2) + "\n", encoding="utf-8"
        )
        time.sleep(1)

        standings_response = requests.get(
            standings_api_url(division_id), headers={"User-Agent": USER_AGENT}, timeout=60
        )
        standings_response.raise_for_status()
        standings = standings_response.json()
        teams = [{
            "team_id": row["teamid"],
            "source_team_name": " ".join(row["Teamname"].split()),
            "team_name": normalize_team_name(row["Teamname"]),
            "team_type": "Varsity division",
        } for row in standings]
        teams.sort(key=lambda row: row["team_name"])
        (raw_directory / f"{stem}_teams.json").write_text(
            json.dumps(teams, indent=2) + "\n", encoding="utf-8"
        )
        metadata = {
            "season": season, "division": gender, "division_id": division_id,
            "schedule_source_url": results_page_url(division_id),
            "schedule_data_url": schedule_api_url(division_id),
            "team_membership_data_url": standings_api_url(division_id),
            "retrieved_at_utc": retrieved_at,
            "schedule_http_status": schedule_response.status_code,
            "standings_http_status": standings_response.status_code,
            "schedule_rows": len(schedule), "varsity_teams": len(teams),
            "membership_rule": "dedicated varsity division",
            "note": "Membership file omits captain and player contact fields.",
        }
        (raw_directory / f"{stem}.metadata.json").write_text(
            json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
        )
        print(f"Saved {season} {gender}: {len(schedule)} rows, {len(teams)} teams")
        time.sleep(1)


if __name__ == "__main__":
    season = sys.argv[1] if len(sys.argv) > 1 else "2025-26"
    collect_season(season)

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests


USER_AGENT = "CollegeSquashStudentProject/0.3 (educational research)"
API_ROOT = "https://api.ussquash.com/resources/divisions"

# 2020-21 is absent: the CSA did not run a normal varsity season during COVID-19.
SEASONS = {
    "2019-20": {"men": 2761, "women": 2762},
    "2021-22": {"men": 3482, "women": 3483},
    "2022-23": {"men": 4054, "women": 4055},
    "2023-24": {"men": 4643, "women": 4644},
    "2024-25": {"men": 5208, "women": 5211},
    "2025-26": {"men": 5733, "women": 5736},
}

MATCH_COLUMNS = [
    "source_id", "date", "season", "division", "division_id",
    "home_team_id", "home_team", "away_team_id", "away_team",
    "home_score", "away_score", "winner", "match_time", "venue_name", "source_url",
    "source_data_url",
]


def schedule_api_url(division_id):
    return f"{API_ROOT}/schedule/{division_id}/"


def standings_api_url(division_id):
    return f"{API_ROOT}/standings/{division_id}"


def results_page_url(division_id):
    return f"https://clublocker.com/divisions/{division_id}/matches"


def normalize_team_name(name):
    name = " ".join(name.split())
    aliases = {
        "Pennsylvania, University of": "University of Pennsylvania",
        "Rochester, University of": "University of Rochester",
        "Virginia, University of": "University of Virginia",
        "Bowdoin College Men": "Bowdoin College",
        "Bowdoin College Women": "Bowdoin College",
        "Dickinson College Men": "Dickinson College",
        "Tufts University Men": "Tufts University",
    }
    return aliases.get(name, name)


def _file_stem(gender, season):
    return f"csa_{gender}_varsity_{season}"


def download_all_sources(raw_directory):
    """Download public CSA schedules and privacy-safe varsity membership files."""
    raw_directory = Path(raw_directory)
    raw_directory.mkdir(parents=True, exist_ok=True)
    retrieved_at = datetime.now(timezone.utc).isoformat()

    for season, divisions in SEASONS.items():
        for gender, division_id in divisions.items():
            schedule_response = requests.get(
                schedule_api_url(division_id), headers={"User-Agent": USER_AGENT}, timeout=60
            )
            schedule_response.raise_for_status()
            schedule = schedule_response.json()
            (raw_directory / f"{_file_stem(gender, season)}.json").write_text(
                json.dumps(schedule, indent=2) + "\n", encoding="utf-8"
            )

            time.sleep(1)
            standings_response = requests.get(
                standings_api_url(division_id), headers={"User-Agent": USER_AGENT}, timeout=60
            )
            standings_response.raise_for_status()
            standings = standings_response.json()

            # Earlier feeds mix team types, so use Club Locker's explicit field.
            separate_varsity_division = season in {"2023-24", "2024-25", "2025-26"}
            teams = []
            for row in standings:
                is_varsity = separate_varsity_division or row.get("CollegeTeamType") == "Varsity"
                if is_varsity:
                    teams.append(
                        {
                            "team_id": row["teamid"],
                            "source_team_name": " ".join(row["Teamname"].split()),
                            "team_name": normalize_team_name(row["Teamname"]),
                            "team_type": row.get("CollegeTeamType") or "Varsity division",
                        }
                    )
            teams.sort(key=lambda row: row["team_name"])
            (raw_directory / f"{_file_stem(gender, season)}_teams.json").write_text(
                json.dumps(teams, indent=2) + "\n", encoding="utf-8"
            )

            metadata = {
                "season": season,
                "division": gender,
                "division_id": division_id,
                "schedule_source_url": results_page_url(division_id),
                "schedule_data_url": schedule_api_url(division_id),
                "team_membership_data_url": standings_api_url(division_id),
                "retrieved_at_utc": retrieved_at,
                "schedule_http_status": schedule_response.status_code,
                "standings_http_status": standings_response.status_code,
                "schedule_rows": len(schedule),
                "varsity_teams": len(teams),
                "membership_rule": (
                    "dedicated varsity division" if separate_varsity_division
                    else "CollegeTeamType equals Varsity in official standings"
                ),
                "note": "Membership file omits captain and player contact fields.",
            }
            (raw_directory / f"{_file_stem(gender, season)}.metadata.json").write_text(
                json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
            )
            time.sleep(1)


def load_division(schedule_path, teams_path, gender, division_id, season):
    raw_matches = json.loads(Path(schedule_path).read_text(encoding="utf-8"))
    varsity_teams = json.loads(Path(teams_path).read_text(encoding="utf-8"))
    varsity_team_ids = {team["team_id"] for team in varsity_teams}
    matches, exclusions, seen_source_ids = [], [], set()

    for row in raw_matches:
        source_id = row.get("scorecardid")
        base_exclusion = {
            "source_id": source_id, "season": season, "division": gender,
            "date": row.get("matchdate"),
            "home_team": normalize_team_name(row.get("wTeamName") or ""),
            "away_team": normalize_team_name(row.get("oTeamName") or ""),
            "raw_status": row.get("Score_Entered"),
            "raw_score": f"{row.get('Home_Matches_Won')}-{row.get('Visitor_Matches_Won')}",
            "source_url": results_page_url(division_id),
        }
        if row.get("Score_Entered") != "Confirmed":
            exclusions.append({**base_exclusion, "reason": "match is not confirmed"})
            continue
        required = [source_id, row.get("matchdate"), row.get("wTeamName"),
                    row.get("oTeamName"), row.get("hteamid"), row.get("vteamid")]
        if any(value is None or value == "" for value in required):
            exclusions.append({**base_exclusion, "reason": "confirmed match is malformed"})
            continue
        home_score, away_score = row.get("Home_Matches_Won"), row.get("Visitor_Matches_Won")
        if not isinstance(home_score, int) or not isinstance(away_score, int):
            exclusions.append({**base_exclusion, "reason": "score is missing or malformed"})
            continue
        if home_score == away_score:
            exclusions.append({**base_exclusion, "reason": "confirmed entry has no match winner"})
            continue
        if row["hteamid"] not in varsity_team_ids and row["vteamid"] not in varsity_team_ids:
            exclusions.append({**base_exclusion, "reason": "neither team is varsity"})
            continue
        if source_id in seen_source_ids:
            raise ValueError(f"Duplicate source ID {source_id} in division {division_id}")
        seen_source_ids.add(source_id)
        home_team = normalize_team_name(row["wTeamName"])
        away_team = normalize_team_name(row["oTeamName"])
        matches.append({
            "source_id": source_id, "date": row["matchdate"], "season": season,
            "division": gender, "division_id": division_id,
            "home_team_id": row["hteamid"], "home_team": home_team,
            "away_team_id": row["vteamid"], "away_team": away_team,
            "home_score": home_score, "away_score": away_score,
            "winner": home_team if home_score > away_score else away_team,
            "match_time": (row.get("MatchTime") or "").strip() or None,
            "venue_name": (row.get("VenueName") or "").strip() or None,
            "source_url": results_page_url(division_id),
            "source_data_url": schedule_api_url(division_id),
        })

    frame = pd.DataFrame(matches, columns=MATCH_COLUMNS)
    exclusions_frame = pd.DataFrame(exclusions)
    if frame.empty:
        raise ValueError(f"No completed matches found for {season} {gender}'s varsity")
    frame["date"] = pd.to_datetime(frame["date"], format="%m/%d/%y")
    return frame.sort_values(["date", "source_id"]).reset_index(drop=True), exclusions_frame, varsity_teams


def load_all_divisions(raw_directory):
    raw_directory = Path(raw_directory)
    all_matches, all_exclusions, all_teams = [], [], []
    for season, divisions in SEASONS.items():
        for gender, division_id in divisions.items():
            stem = _file_stem(gender, season)
            matches, exclusions, teams = load_division(
                raw_directory / f"{stem}.json", raw_directory / f"{stem}_teams.json",
                gender, division_id, season,
            )
            all_matches.append(matches)
            all_exclusions.append(exclusions)
            all_teams.extend({**team, "season": season, "division": gender,
                              "division_id": division_id} for team in teams)
    matches = pd.concat(all_matches, ignore_index=True)
    exclusions = pd.concat(all_exclusions, ignore_index=True)
    teams = pd.DataFrame(all_teams)
    if matches["source_id"].duplicated().any():
        ids = matches.loc[matches["source_id"].duplicated(False), "source_id"]
        raise ValueError(f"Duplicate source IDs across divisions: {ids.tolist()}")
    # Same teams can legitimately play twice on one date. Match time separates
    # those doubleheaders while source IDs remain the primary provenance key.
    key = ["date", "division_id", "home_team_id", "away_team_id", "match_time"]
    if matches.duplicated(key).any():
        rows = matches.loc[matches.duplicated(key, False), key]
        raise ValueError(f"Duplicate matches found:\n{rows.to_string(index=False)}")
    return (
        matches.sort_values(["date", "division", "source_id"]).reset_index(drop=True),
        exclusions.reset_index(drop=True),
        teams.sort_values(["season", "division", "team_name"]).reset_index(drop=True),
    )


def calculate_team_record(matches, team, division, season=None):
    selected = matches.loc[matches["division"] == division]
    if season is not None:
        selected = selected.loc[selected["season"] == season]
    team_matches = selected.loc[
        (selected["home_team"] == team) | (selected["away_team"] == team)
    ]
    if team_matches.empty:
        raise ValueError(f"No {division}'s matches found for {team}")
    wins = int((team_matches["winner"] == team).sum())
    total = len(team_matches)
    return {"team": team, "division": division, "season": season,
            "wins": wins, "losses": total - wins, "total_matches": total,
            "win_percentage": wins / total}


if __name__ == "__main__":
    download_all_sources("data/raw")
    print(f"Saved official CSA data for {', '.join(SEASONS)}.")

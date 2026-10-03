import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup


TEAM = "Harvard Men"
SEASON = "2024-25"
SOURCE_URL = "https://gocrimson.com/sports/mens-squash/schedule/2024-25"
DATE_PATTERN = re.compile(r"- ([A-Z][a-z]+ \d{1,2}, \d{4})$")
SCORE_PATTERN = re.compile(r"\b([WL]),\s*(\d+)-(\d+)\b")


def _text(element):
    return element.get_text(" ", strip=True) if element else ""


def parse_schedule(html):
    """Return completed matches and explicitly excluded schedule entries."""
    soup = BeautifulSoup(html, "html.parser")
    matches = []
    exclusions = []

    for game in soup.select("li.sidearm-schedule-game"):
        source_id = game.get("data-game-id")
        opponent = _text(game.select_one(".sidearm-schedule-game-opponent-name a"))
        if not opponent:
            opponent = _text(game.select_one(".sidearm-schedule-game-opponent-name"))
            opponent = re.sub(r"^No\.\s*\d+\s*", "", opponent).strip()

        result_text = _text(game.select_one(".sidearm-schedule-game-result"))
        score_match = SCORE_PATTERN.search(result_text)
        toggle_text = _text(game.select_one(".sidearm-schedule-game-toggle"))
        date_match = DATE_PATTERN.search(toggle_text)

        if not score_match:
            exclusions.append(
                {
                    "source_id": source_id,
                    "opponent_or_event": opponent,
                    "raw_result": result_text or None,
                    "reason": "not a completed team match with a W/L score",
                    "source_url": SOURCE_URL,
                }
            )
            continue

        if not opponent or not date_match or not source_id:
            raise ValueError(f"Malformed completed match in source (game id {source_id})")

        result, team_score, opponent_score = score_match.groups()
        team_score = int(team_score)
        opponent_score = int(opponent_score)
        if (result == "W") != (team_score > opponent_score):
            raise ValueError(f"Result and score disagree for game id {source_id}")
        if team_score == opponent_score:
            raise ValueError(f"Team match cannot end in a tie (game id {source_id})")

        location_marker = _text(game.select_one(".sidearm-schedule-game-conference-vs"))
        venue = {"vs": "home", "at": "away"}.get(location_marker, "neutral")
        matches.append(
            {
                "source_id": source_id,
                "date": date_match.group(1),
                "season": SEASON,
                "team": TEAM,
                "opponent": opponent,
                "venue": venue,
                "result": result,
                "team_score": team_score,
                "opponent_score": opponent_score,
                "source_url": SOURCE_URL,
            }
        )

    matches_frame = pd.DataFrame(matches)
    exclusions_frame = pd.DataFrame(exclusions)
    if matches_frame.empty:
        raise ValueError("No completed team matches found")

    matches_frame["date"] = pd.to_datetime(matches_frame["date"], format="%B %d, %Y")
    duplicate_keys = ["date", "team", "opponent"]
    duplicates = matches_frame.duplicated(duplicate_keys, keep=False)
    if duplicates.any():
        duplicate_rows = matches_frame.loc[duplicates, duplicate_keys]
        raise ValueError(f"Duplicate matches found:\n{duplicate_rows.to_string(index=False)}")

    matches_frame = matches_frame.sort_values("date").reset_index(drop=True)
    return matches_frame, exclusions_frame


def calculate_record(matches, team=TEAM):
    team_matches = matches.loc[matches["team"] == team]
    if team_matches.empty:
        raise ValueError(f"No matches found for {team}")

    wins = int((team_matches["result"] == "W").sum())
    losses = int((team_matches["result"] == "L").sum())
    total_matches = len(team_matches)
    if wins + losses != total_matches:
        raise ValueError("Every completed match must be a win or loss")

    return {
        "team": team,
        "wins": wins,
        "losses": losses,
        "total_matches": total_matches,
        "win_percentage": wins / total_matches,
    }


def load_schedule(path):
    html = Path(path).read_text(encoding="utf-8")
    return parse_schedule(html)


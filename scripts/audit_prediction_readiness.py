"""Audit current rosters and preseason prediction readiness without downloading data."""
import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from college_squash.database import connect_database
from college_squash.preseason import CURRENT_SEASON, MINIMUM_PLAYABLE_ROSTER, preseason_lineup


def audit(database_path):
    rows = []
    with connect_database(database_path) as connection:
        teams = connection.execute("""
            SELECT gender, team_name, COUNT(*) roster_size,
                   COUNT(current_rating) rated_players
            FROM current_roster_players WHERE season=?
            GROUP BY gender, team_name ORDER BY gender, team_name
        """, (CURRENT_SEASON,)).fetchall()
        for team in teams:
            lineup, confidence = preseason_lineup(connection, team["team_name"], team["gender"])
            rated = team["rated_players"]
            forfeits = max(0, 9 - rated) if rated >= MINIMUM_PLAYABLE_ROSTER else 0
            mode = "fallback" if lineup is None else ("short-roster lineup" if forfeits else "normal lineup")
            reasons = []
            if rated < team["roster_size"]:
                reasons.append(f"{team['roster_size'] - rated} missing rating(s)")
            if rated < MINIMUM_PLAYABLE_ROSTER:
                reasons.append("below seven rated players")
            rows.append({**dict(team), "forfeited_positions": forfeits, "readiness": mode,
                         "lineup_confidence": confidence, "reason": "; ".join(reasons) or None})
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="data/college_squash.db")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = audit(Path(args.database))
    text = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)

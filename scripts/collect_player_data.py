from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import sqlite3
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from college_squash.players import API_ROOT, download_json


def main():
    database_path = PROJECT_ROOT / "data/college_squash.db"
    raw_path = PROJECT_ROOT / "data/raw"
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    matches = connection.execute(
        "SELECT source_match_id FROM matches ORDER BY source_match_id"
    ).fetchall()
    teams = connection.execute(
        "SELECT DISTINCT division_id, team_id FROM teams ORDER BY division_id, team_id"
    ).fetchall()
    connection.close()

    failures = []

    def fetch_scorecard(match_id):
        try:
            download_json(
                f"{API_ROOT}/leagues/scorecards/{match_id}/list",
                raw_path / "player_scorecards" / f"{match_id}.json",
                delay=0.1,
            )
        except Exception as error:
            return {"kind": "scorecard", "id": match_id, "error": str(error)}

    # Four workers keep collection practical while remaining gentle to the public API.
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(fetch_scorecard, int(row["source_match_id"])) for row in matches]
        for number, future in enumerate(as_completed(futures), start=1):
            failure = future.result()
            if failure:
                failures.append(failure)
            if number % 100 == 0:
                print(f"Scorecards: {number}/{len(matches)} ({len(failures)} failures)", flush=True)

    def fetch_roster(division_id, team_id):
        try:
            download_json(
                f"{API_ROOT}/teams/{team_id}/players",
                raw_path / "player_rosters" / f"{division_id}_{team_id}.json",
                delay=0.1,
            )
        except Exception as error:
            return {"kind": "roster", "id": team_id, "error": str(error)}

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(fetch_roster, int(row["division_id"]), int(row["team_id"]))
            for row in teams
        ]
        for number, future in enumerate(as_completed(futures), start=1):
            failure = future.result()
            if failure:
                failures.append(failure)
            if number % 100 == 0:
                print(f"Rosters: {number}/{len(teams)} ({len(failures)} failures)", flush=True)

    (raw_path / "player_download_failures.json").write_text(
        json.dumps(failures, indent=2), encoding="utf-8"
    )
    (raw_path / "player_data.metadata.json").write_text(json.dumps({
        "source": "College Squash Association / Club Locker public API",
        "scorecard_endpoint": f"{API_ROOT}/leagues/scorecards/{{scorecard_id}}/list",
        "roster_endpoint": f"{API_ROOT}/teams/{{team_id}}/players",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "scorecards_requested": len(matches), "rosters_requested": len(teams),
        "failures": len(failures),
        "notes": "CurrentRating and Rating are intentionally not imported because they are not historically dated.",
    }, indent=2), encoding="utf-8")
    print(f"Finished with {len(failures)} failures")


if __name__ == "__main__":
    main()

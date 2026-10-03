from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from college_squash.players import download_json
from college_squash.ratings import RATING_HISTORY_URL


def main():
    connection = sqlite3.connect(PROJECT_ROOT / "data/college_squash.db")
    player_ids = [row[0] for row in connection.execute("SELECT player_id FROM players ORDER BY player_id")]
    connection.close()
    raw_directory = PROJECT_ROOT / "data/raw"

    def fetch(player_id):
        try:
            download_json(
                RATING_HISTORY_URL.format(player_id=player_id),
                raw_directory / "player_season_rankings" / f"{player_id}.json",
                delay=0.1,
            )
        except Exception as error:
            return {"player_id": player_id, "error": str(error)}

    failures = []
    # The endpoint is read-only and responses are small. Eight workers still keep
    # request volume modest while avoiding an hour-long reproducibility run.
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(fetch, player_id) for player_id in player_ids]
        for number, future in enumerate(as_completed(futures), start=1):
            failure = future.result()
            if failure:
                failures.append(failure)
            if number % 100 == 0:
                print(f"Rating histories: {number}/{len(player_ids)} ({len(failures)} failures)", flush=True)

    retrieved_at = datetime.now(timezone.utc).isoformat()
    (raw_directory / "player_season_rankings.metadata.json").write_text(json.dumps({
        "source": "Club Locker public Season Rankings archive",
        "endpoint": RATING_HISTORY_URL,
        "retrieved_at_utc": retrieved_at,
        "players_requested": len(player_ids),
        "failures": failures,
        "interpretation": (
            "RankingPeriod is the weekly ranking snapshot date shown by Club Locker. "
            "A match on date D may use only a snapshot with RankingPeriod strictly before D."
        ),
    }, indent=2), encoding="utf-8")
    print(f"Finished with {len(failures)} failures")


if __name__ == "__main__":
    main()

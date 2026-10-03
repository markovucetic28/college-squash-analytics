"""Evaluate immutable pre-match snapshots after official results become available."""

from pathlib import Path
import json, os, sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from college_squash.database import connect_database
from college_squash.live_season import ensure_live_schema, prospective_metrics

DATABASE_PATH = Path(os.environ.get("COLLEGE_SQUASH_DB", PROJECT_ROOT / "data/college_squash.db"))


def main():
    with connect_database(DATABASE_PATH) as connection:
        ensure_live_schema(connection)
        rows = connection.execute("""
            SELECT ps.prediction_mode mode, ps.team_one_probability probability,
                   CASE WHEN lm.away_score > lm.home_score THEN 1 ELSE 0 END outcome
            FROM prediction_snapshots ps JOIN live_matches lm ON lm.source_match_id=ps.fixture_id
            WHERE lm.status='completed' AND ps.team_one_probability IS NOT NULL
        """).fetchall()
    modes = sorted({row["mode"] for row in rows})
    report = {mode: prospective_metrics([dict(row) for row in rows if row["mode"] == mode])
              for mode in modes}
    output = PROJECT_ROOT / "data/processed/live_prediction_evaluation.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__": main()

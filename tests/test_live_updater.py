import hashlib
import json
import sqlite3
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from update_current_season import commit_database, rating_refresh_needed


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_incremental_rating_refresh_skips_unchanged_and_preserves_history(tmp_path):
    path = tmp_path / "1.json"
    path.write_text(json.dumps([{"RankingPeriod": "2026-10-01", "NewRating": 6.25}]))
    assert rating_refresh_needed(path, 6.25) is False
    assert rating_refresh_needed(path, 6.30) is True
    assert json.loads(path.read_text())[0]["NewRating"] == 6.25


def test_failed_database_update_leaves_original_untouched(tmp_path):
    database = tmp_path / "live.db"
    sqlite3.connect(database).close()
    before = digest(database)
    match = {"source_match_id": 10, "season": "2026-27", "gender": "men",
             "division_id": 6376, "match_date": "2026-11-01", "home_team_id": 1,
             "home_team": "A", "away_team_id": 2, "away_team": "B",
             "status": "completed", "home_score": 5, "away_score": 4,
             "source_url": "https://example.test/10"}
    with pytest.raises(ValueError):
        commit_database(database, [match], {10: []}, {})
    assert digest(database) == before
    assert not database.with_suffix(".db.live.tmp").exists()


def test_live_update_does_not_modify_model_artifacts(tmp_path):
    project = Path(__file__).resolve().parents[1]
    player = project / "data/preseason_player_model.joblib"
    team = project / "data/matchup_model.joblib"
    before = (digest(player), digest(team))
    database = tmp_path / "live.db"
    sqlite3.connect(database).close()
    commit_database(database, [], {}, {})
    assert (digest(player), digest(team)) == before

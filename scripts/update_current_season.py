"""Incrementally refresh 2026-27 data and transactionally update live SQLite state."""

from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
import argparse, json, os, shutil, sys, time
import requests
import joblib
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from college_squash.clublocker import USER_AGENT, normalize_team_name, schedule_api_url, standings_api_url
from college_squash.database import connect_database
from college_squash.live_season import ensure_live_schema, save_prediction_snapshot, stable_hash, store_complete_scorecard, upsert_live_match, utc_now
from college_squash.players import API_ROOT, parse_scorecard_rows
from college_squash.preseason import predict_current_season_matchup, predict_preseason_matchup, sync_current_rosters
from college_squash.ratings import RATING_HISTORY_URL

SEASON = "2026-27"
DIVISIONS = {"men": 6376, "women": 6379}
MINIMUM_LINEUPS = 3
DATABASE_PATH = Path(os.environ.get("COLLEGE_SQUASH_DB", PROJECT_ROOT / "data/college_squash.db"))


def get_json(url):
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
    response.raise_for_status()
    time.sleep(.1)
    return response.json()


def write_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def replace_snapshot(path, rows, archive_root, timestamp):
    path = Path(path)
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        if old == rows:
            return False
        archive = Path(archive_root) / timestamp / path.name
        archive.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, archive)
    return write_json(path, rows)


def complete_scorecard(rows):
    positions = {row.get("positionPlayed") for row in rows
                 if row.get("status") == "C" and row.get("winner") in {"H", "V"}}
    return positions == {f"{number}S" for number in range(1, 10)}


def normalized_match(row, gender, division_id, retrieved_at):
    completed = row.get("Score_Entered") == "Confirmed"
    return {
        "source_match_id": int(row["scorecardid"]), "season": SEASON,
        "gender": gender, "division_id": division_id,
        "match_date": datetime.strptime(row["matchdate"], "%m/%d/%y").strftime("%Y-%m-%d"),
        "match_time": (row.get("MatchTime") or "").strip() or None,
        "home_team_id": int(row["hteamid"]), "home_team": normalize_team_name(row["wTeamName"]),
        "away_team_id": int(row["vteamid"]), "away_team": normalize_team_name(row["oTeamName"]),
        "venue_name": (row.get("VenueName") or "").strip() or None,
        "status": "completed" if completed else "scheduled",
        "home_score": int(row.get("Home_Matches_Won") or 0) if completed else None,
        "away_score": int(row.get("Visitor_Matches_Won") or 0) if completed else None,
        "source_url": f"https://clublocker.com/divisions/{division_id}/matches",
        "source_hash": stable_hash(row), "retrieved_at_utc": retrieved_at,
    }


def rating_refresh_needed(path, current_rating):
    path = Path(path)
    if not path.exists(): return True
    if current_rating in (None, "", 0, "0"): return False
    values = []
    for row in json.loads(path.read_text(encoding="utf-8")):
        try: values.append((pd.Timestamp(row.get("RankingPeriod")), float(row.get("NewRating"))))
        except (TypeError, ValueError): pass
    if not values: return True
    latest_rating = max(values, key=lambda item: item[0])[1]
    return abs(latest_rating - float(current_rating)) > .0001


def snapshot_upcoming(connection):
    """Store one immutable forecast per mode for fixtures in the next 14 days."""
    artifact = joblib.load(PROJECT_ROOT / "data/preseason_player_model.joblib")
    start = datetime.now(timezone.utc).date(); end = start + timedelta(days=14)
    created = 0
    for fixture in connection.execute(
        "SELECT * FROM live_matches WHERE status='scheduled' AND match_date BETWEEN ? AND ?",
        (start.isoformat(), end.isoformat()),
    ):
        result = predict_current_season_matchup(connection, artifact, fixture["away_team"], fixture["home_team"], fixture["gender"])
        if result is None:
            result = predict_preseason_matchup(connection, artifact, fixture["away_team"], fixture["home_team"], fixture["gender"])
        if result is None: continue
        mode = "projected" if result["mode"].startswith("Current-season") else "preseason"
        projection = {"mode": mode, "team_one_probability": float(result["team_one_probability"]),
            "team_one_expected_wins": float(result["team_one_expected_wins"]),
            "lineup_confidence": float(result["lineup_confidence"]),
            "pairings": result["pairings"].to_dict("records")}
        save_prediction_snapshot(connection, fixture["source_match_id"], projection)
        created += 1
    return created


def commit_database(database_path, matches, scorecards, summary):
    """Apply one refresh to a copy and replace the live database only after validation."""
    database_path = Path(database_path)
    staging = database_path.with_suffix(database_path.suffix + ".live.tmp")
    staging.unlink(missing_ok=True); shutil.copy2(database_path, staging)
    connection = connect_database(staging)
    try:
        ensure_live_schema(connection); connection.execute("BEGIN")
        sync_current_rosters(connection, PROJECT_ROOT / "data/raw")
        for match in matches: upsert_live_match(connection, match)
        for match_id, rows in scorecards.items(): store_complete_scorecard(connection, match_id, rows)
        summary["prediction_snapshots_created"] = snapshot_upcoming(connection)
        now = utc_now()
        connection.execute("INSERT INTO refresh_runs(started_at_utc,completed_at_utc,status,summary_json) VALUES (?,?,'success',?)",
                           (now, now, json.dumps(summary, sort_keys=True)))
        connection.commit()
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("SQLite integrity check failed")
    except Exception:
        connection.rollback(); connection.close(); staging.unlink(missing_ok=True); raise
    connection.close(); os.replace(staging, database_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--schedules-only", action="store_true")
    parser.add_argument("--rosters-only", action="store_true")
    parser.add_argument("--from-cache", action="store_true",
                        help="Validate and apply existing raw snapshots without network requests.")
    args = parser.parse_args()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    retrieved_at = datetime.now(timezone.utc).isoformat()
    current_raw = PROJECT_ROOT / "data/raw" / f"current_{SEASON}"
    scorecard_hash_path = current_raw / "scorecard_source_hashes.json"
    scorecard_hashes = json.loads(scorecard_hash_path.read_text()) if scorecard_hash_path.exists() else {}
    active, roster_ratings, matches, scorecards = set(), {}, [], {}
    lineups, warnings, counts = Counter(), [], Counter()

    for gender, division_id in DIVISIONS.items():
        schedule_path = current_raw / f"csa_{gender}_varsity_{SEASON}.json"
        teams_path = current_raw / f"csa_{gender}_varsity_{SEASON}_teams.json"
        if args.rosters_only or args.from_cache:
            schedule, teams = json.loads(schedule_path.read_text()), json.loads(teams_path.read_text())
        else:
            schedule, teams = get_json(schedule_api_url(division_id)), get_json(standings_api_url(division_id))
            counts["schedule_changes"] += write_json(schedule_path, schedule)
            write_json(teams_path, teams)
            write_json(current_raw / f"csa_{gender}_varsity_{SEASON}.metadata.json", {
                "season": SEASON, "gender": gender, "division_id": division_id,
                "retrieved_at_utc": retrieved_at, "schedule_data_url": schedule_api_url(division_id),
                "standings_data_url": standings_api_url(division_id),
                "schedule_rows": len(schedule), "team_rows": len(teams),
            })
        counts["schedules_checked"] += len(schedule)
        varsity = {int(team["teamid"]) for team in teams if team.get("teamid")}
        for row in schedule:
            try:
                if int(row["hteamid"]) in varsity or int(row["vteamid"]) in varsity:
                    matches.append(normalized_match(row, gender, division_id, retrieved_at))
            except (KeyError, TypeError, ValueError) as error:
                warnings.append({"source_match_id": row.get("scorecardid"), "reason": str(error)})
        if args.schedules_only: continue

        for team in teams:
            team_id = int(team["teamid"])
            path = PROJECT_ROOT / "data/raw/player_rosters" / f"{division_id}_{team_id}.json"
            if args.from_cache:
                if not path.exists():
                    warnings.append({"team_id": team_id, "reason": "cached roster missing"}); continue
                roster = json.loads(path.read_text(encoding="utf-8"))
            else:
                roster = get_json(f"{API_ROOT}/teams/{team_id}/players")
            previous = {int(row.get("playerid") or 0) for row in json.loads(path.read_text())} if path.exists() else set()
            replace_snapshot(path, roster, PROJECT_ROOT / "data/raw/player_rosters_archive", timestamp)
            current = {int(row.get("playerid") or 0) for row in roster} - {0}
            counts["new_players"] += len(current - previous); active.update(current)
            roster_ratings.update({int(row["playerid"]): row.get("CurrentRating") for row in roster if row.get("playerid")})
        if args.rosters_only: continue

        for source in schedule:
            if source.get("Score_Entered") != "Confirmed" or not source.get("scorecardid"): continue
            match_id = int(source["scorecardid"]); path = PROJECT_ROOT / "data/raw/player_scorecards" / f"{match_id}.json"
            source_hash = stable_hash(source)
            if path.exists() and scorecard_hashes.get(str(match_id)) == source_hash:
                rows = json.loads(path.read_text(encoding="utf-8"))
            elif args.from_cache and path.exists():
                rows = json.loads(path.read_text(encoding="utf-8"))
            else:
                rows = get_json(f"{API_ROOT}/leagues/scorecards/{match_id}/list")
                changed = replace_snapshot(path, rows, PROJECT_ROOT / "data/raw/player_scorecards_archive", timestamp)
                counts["new_scorecards" if str(match_id) not in scorecard_hashes else "changed_scorecards"] += int(changed)
                scorecard_hashes[str(match_id)] = source_hash
            active.update(int(row.get(key) or 0) for row in rows for key in ("wid1", "oid1") if int(row.get(key) or 0) > 0)
            if not complete_scorecard(rows):
                warnings.append({"source_match_id": match_id, "reason": "incomplete scorecard"}); continue
            try:
                match = next(item for item in matches if item["source_match_id"] == match_id)
                scorecards[match_id] = parse_scorecard_rows(rows, match)
                lineups.update((int(source["hteamid"]), int(source["vteamid"])))
            except (ValueError, KeyError, TypeError) as error:
                warnings.append({"source_match_id": match_id, "reason": str(error)})

    ratings_refreshed = 0
    if not args.schedules_only and not args.rosters_only and not args.from_cache:
        for player_id in sorted(active):
            path = PROJECT_ROOT / "data/raw/player_season_rankings" / f"{player_id}.json"
            if not rating_refresh_needed(path, roster_ratings.get(player_id)): continue
            rows = get_json(RATING_HISTORY_URL.format(player_id=player_id))
            ratings_refreshed += replace_snapshot(path, rows, PROJECT_ROOT / "data/raw/player_season_rankings_archive", timestamp)

    ready = sorted(team for team, count in lineups.items() if count >= MINIMUM_LINEUPS)
    summary = {**counts, "season": SEASON, "retrieved_at_utc": retrieved_at,
        "completed_team_matches": sum(row["status"] == "completed" for row in matches),
        "complete_scorecards": len(scorecards), "individual_matches_added": len(scorecards) * 9,
        "ratings_refreshed": ratings_refreshed, "teams_with_lineup_evidence": len(lineups),
        "projected_ready_teams": len(ready), "teams_ready_for_projected_mode": ready,
        "last_schedule_refresh": retrieved_at, "last_rating_refresh": retrieved_at if ratings_refreshed else None,
        "warnings": warnings}
    if not args.schedules_only and not args.rosters_only:
        commit_database(DATABASE_PATH, matches, scorecards, summary)
        write_json(scorecard_hash_path, scorecard_hashes)
    write_json(PROJECT_ROOT / "data/processed/current_season_readiness.json", summary)
    write_json(PROJECT_ROOT / "data/processed/current_season_update_summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__": main()

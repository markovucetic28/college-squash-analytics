from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from college_squash.database import build_database


def main():
    database_path = PROJECT_ROOT / "data/college_squash.db"
    counts = build_database(PROJECT_ROOT / "data/raw", database_path)
    print(f"Built {database_path}")
    print(f"Sources: {counts['sources']}")
    print(f"Divisions: {counts['divisions']}")
    print(f"Programs: {counts['programs']}")
    print(f"Teams: {counts['teams']} ({counts['varsity_teams']} varsity)")
    print(f"Matches: {counts['matches']}")
    print(f"Source exclusions not loaded: {counts['exclusions']}")
    print(f"Players named from official rosters: {counts['players']}")
    print(f"Individual matches: {counts['individual_matches']}")
    print(f"Player scorecards excluded: {counts['player_exclusions']}")
    print(f"Historical rating snapshots: {counts['ratings']}")
    print(f"Players without valid rating history: {counts['rating_exclusions']}")
    print(f"Current scheduled matches: {counts['scheduled_matches']}")
    print(f"Current schedule exclusions: {counts['scheduled_exclusions']}")
    print(f"Current roster players: {counts['current_roster_players']}")


if __name__ == "__main__":
    main()

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from college_squash.analytics import head_to_head, season_history, team_summary
from college_squash.database import connect_database


def main():
    parser = argparse.ArgumentParser(description="Show analytics for one varsity squash team.")
    parser.add_argument("team", help="Canonical team name, such as Harvard University")
    parser.add_argument("--gender", choices=["men", "women"], required=True)
    parser.add_argument("--season", help="Season such as 2024-25; omit for program history")
    parser.add_argument("--opponent", help="Optional opponent for a head-to-head record")
    args = parser.parse_args()

    database_path = PROJECT_ROOT / "data/college_squash.db"
    with connect_database(database_path) as connection:
        summary = team_summary(connection, args.team, args.gender, args.season)
        history = season_history(connection, args.team, args.gender, args.season)
        label = args.season or "all available seasons"
        print(f"{args.team} ({args.gender}, {label})")
        print(f"Record: {summary['wins']}-{summary['losses']}")
        print(f"Win percentage: {summary['win_percentage']:.1%}")
        print(f"Recent form: {summary['recent_form']} (oldest to newest)")
        print(f"Average score: {summary['average_team_score']:.2f}")
        print(f"Average opponent score: {summary['average_opponent_score']:.2f}")
        print(f"Average margin: {summary['average_margin']:+.2f}")
        if args.opponent:
            record = head_to_head(connection, args.team, args.opponent, args.gender, args.season)
            print(
                f"Head-to-head vs {args.opponent}: "
                f"{record['team_one_wins']}-{record['team_two_wins']}"
            )
        print("\nMatch history")
        print(history[["season", "date", "opponent", "result", "team_score", "opponent_score"]].to_string(index=False))


if __name__ == "__main__":
    main()

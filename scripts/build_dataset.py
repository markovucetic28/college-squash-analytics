from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from college_squash.clublocker import calculate_team_record, load_all_divisions


RAW_DIRECTORY = PROJECT_ROOT / "data/raw"
MATCHES_PATH = PROJECT_ROOT / "data/processed/csa_varsity_all_seasons_matches.csv"
EXCLUSIONS_PATH = PROJECT_ROOT / "data/processed/csa_varsity_all_seasons_exclusions.csv"
TEAMS_PATH = PROJECT_ROOT / "data/processed/csa_varsity_all_seasons_teams.csv"


def main():
    matches, exclusions, teams = load_all_divisions(RAW_DIRECTORY)
    MATCHES_PATH.parent.mkdir(parents=True, exist_ok=True)
    matches.to_csv(MATCHES_PATH, index=False, date_format="%Y-%m-%d")
    exclusions.to_csv(EXCLUSIONS_PATH, index=False)
    teams.to_csv(TEAMS_PATH, index=False)

    print(f"Clean matches: {len(matches)}")
    print(f"Varsity teams: {len(teams)}")
    print(f"Excluded entries: {len(exclusions)}")
    print(f"Date range: {matches['date'].min():%Y-%m-%d} to {matches['date'].max():%Y-%m-%d}")
    for team, division in [
        ("Harvard University", "men"),
        ("University of Pennsylvania", "men"),
        ("Trinity College", "women"),
    ]:
        record = calculate_team_record(matches, team, division, "2024-25")
        print(
            f"{team} ({division}): {record['wins']}-{record['losses']} "
            f"({record['win_percentage']:.1%})"
        )
    print(f"Wrote {MATCHES_PATH}")


if __name__ == "__main__":
    main()

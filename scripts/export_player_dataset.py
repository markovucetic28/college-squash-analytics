from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from college_squash.clublocker import load_all_divisions
from college_squash.players import load_player_dataset


def main():
    matches, _, _ = load_all_divisions(PROJECT_ROOT / "data/raw")
    individuals, exclusions = load_player_dataset(PROJECT_ROOT / "data/raw", matches)
    output = PROJECT_ROOT / "data/processed"
    individuals.to_csv(output / "individual_matches_all_seasons.csv", index=False)
    exclusions.to_csv(output / "individual_match_exclusions.csv", index=False)
    print(f"Validated team scorecards: {individuals['source_match_id'].nunique()}")
    print(f"Individual matches: {len(individuals)}")
    print(f"Excluded or unavailable team scorecards: {len(exclusions)}")


if __name__ == "__main__":
    main()

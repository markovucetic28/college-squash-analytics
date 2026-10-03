from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from college_squash.database import connect_database
from college_squash.preseason import sync_current_rosters


def main():
    with connect_database(PROJECT_ROOT / "data/college_squash.db") as connection:
        count = sync_current_rosters(connection, PROJECT_ROOT / "data/raw")
    print(f"Loaded {count} official 2026-27 roster players")


if __name__ == "__main__":
    main()

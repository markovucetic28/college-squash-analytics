from pathlib import Path
import json
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from college_squash.database import connect_database
def main():
    output_directory = PROJECT_ROOT / "data/processed"
    database_path = PROJECT_ROOT / "data/college_squash.db"

    connection = connect_database(database_path)
    ratings = pd.read_sql_query(
        "SELECT * FROM player_ratings ORDER BY player_id, rating_date", connection
    )
    exclusions = pd.read_sql_query(
        """
        SELECT p.player_id, 'no_valid_history' reason
        FROM players p
        LEFT JOIN player_ratings r ON r.player_id=p.player_id
        WHERE r.player_id IS NULL
        ORDER BY p.player_id
        """,
        connection,
    )
    ratings.to_csv(output_directory / "historical_player_ratings.csv", index=False)
    exclusions.to_csv(output_directory / "historical_player_rating_exclusions.csv", index=False)

    mapped = pd.read_sql_query(
        """
        SELECT i.individual_match_id, i.source_match_id, i.position,
               i.home_player_id, i.away_player_id, m.match_date, m.season,
               d.gender, r.home_rating_date, r.home_rating,
               r.home_rating_age_days, r.away_rating_date, r.away_rating,
               r.away_rating_age_days, r.rating_difference_home,
               r.both_ratings_available
        FROM individual_matches i
        JOIN matches m ON m.source_match_id=i.source_match_id
        JOIN divisions d ON d.division_id=m.division_id
        JOIN individual_match_ratings r
          ON r.individual_match_id=i.individual_match_id
        ORDER BY m.match_date, i.source_match_id, i.position
        """,
        connection,
    )
    connection.close()
    mapped.to_csv(
        output_directory / "individual_match_historical_ratings.csv", index=False
    )

    coverage = mapped.groupby(["season", "gender"]).agg(
        individual_matches=("individual_match_id", "size"),
        matches_with_both_ratings=("both_ratings_available", "sum"),
        median_home_rating_age_days=("home_rating_age_days", "median"),
        median_away_rating_age_days=("away_rating_age_days", "median"),
    ).reset_index()
    coverage["both_ratings_coverage"] = (
        coverage["matches_with_both_ratings"] / coverage["individual_matches"]
    )
    coverage.to_csv(output_directory / "historical_rating_coverage.csv", index=False)

    available_ages = pd.concat([
        mapped["home_rating_age_days"], mapped["away_rating_age_days"]
    ]).dropna()
    summary = {
        "rating_snapshots": int(len(ratings)),
        "players_with_history": int(ratings["player_id"].nunique()),
        "raw_histories_excluded": int(len(exclusions)),
        "individual_matches": int(len(mapped)),
        "individual_matches_with_both_ratings": int(mapped["both_ratings_available"].sum()),
        "both_ratings_coverage": float(mapped["both_ratings_available"].mean()),
        "median_rating_age_days": float(available_ages.median()),
        "same_day_ratings_used": int(
            ((mapped["home_rating_age_days"] == 0) | (mapped["away_rating_age_days"] == 0)).sum()
        ),
        "coverage": coverage.to_dict(orient="records"),
    }
    (output_directory / "historical_rating_coverage.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

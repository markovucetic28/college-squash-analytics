import json
from pathlib import Path

import pandas as pd


RATING_HISTORY_URL = (
    "https://api.ussquash.com/resources/res/user/{player_id}/rankings?history=yes"
)


def rating_season(rating_date):
    date = pd.Timestamp(rating_date)
    start = date.year if date.month >= 7 else date.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def parse_rating_history(rows, player_id, retrieved_at_utc):
    candidates = {}
    for row in rows:
        try:
            group_id = int(row.get("RankingGroupId") or row.get("Rating_GroupID") or 0)
        except (TypeError, ValueError):
            continue
        if group_id not in {1, 2, 208}:
            continue
        try:
            rating_date = pd.Timestamp(row.get("RankingPeriod")).normalize()
            rating = float(row.get("NewRating"))
        except (TypeError, ValueError):
            continue
        if pd.isna(rating_date) or rating <= 0:
            continue
        try:
            division_id = int(row.get("DivisionID") or 0)
        except (TypeError, ValueError):
            division_id = 0
        group_priority = {208: 0, 1: 1, 2: 2}[group_id]
        division_priority = 0 if division_id == 0 else 1 if division_id in {2, 3} else 2
        candidate = {
            "player_id": int(player_id),
            "rating_date": rating_date,
            "rating": float(rating),
            "season": rating_season(rating_date),
            "ranking_group_id": group_id,
            "rating_group": row.get("RatingGroupDescr"),
            "division_id": division_id,
            "source_season": row.get("Season"),
            "source_url": RATING_HISTORY_URL.format(player_id=player_id),
            "retrieved_at_utc": retrieved_at_utc,
            "_priority": (group_priority, division_priority),
        }
        previous = candidates.get(rating_date)
        if previous is None or candidate["_priority"] < previous["_priority"]:
            candidates[rating_date] = candidate
    frame = pd.DataFrame(candidates.values())
    if frame.empty:
        return frame
    # The archive repeats one underlying rating across ranking organizations and
    # divisions. Prefer the Universal archive, then US Squash, then CSA, and prefer
    # all-player/all-gender divisions over age groups. This avoids averaging rounded
    # display values from duplicate rows.
    return frame[[
        "player_id", "rating_date", "rating", "season", "ranking_group_id",
        "rating_group", "division_id", "source_season", "source_url", "retrieved_at_utc",
    ]].sort_values("rating_date")


def load_rating_histories(raw_directory):
    raw_directory = Path(raw_directory)
    metadata_path = raw_directory / "player_season_rankings.metadata.json"
    if not metadata_path.exists():
        return pd.DataFrame(), pd.DataFrame()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    frames, exclusions = [], []
    for path in sorted((raw_directory / "player_season_rankings").glob("*.json")):
        player_id = int(path.stem)
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
            frame = parse_rating_history(rows, player_id, metadata["retrieved_at_utc"])
            if frame.empty:
                exclusions.append({"player_id": player_id, "reason": "no_valid_history"})
            else:
                frames.append(frame)
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            exclusions.append({"player_id": player_id, "reason": str(error)})
    ratings = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return ratings, pd.DataFrame(exclusions)


def latest_rating_strictly_before(ratings, player_id, match_date):
    date = pd.Timestamp(match_date).normalize()
    available = ratings[
        (ratings["player_id"] == int(player_id)) & (ratings["rating_date"] < date)
    ]
    if available.empty:
        return None
    return available.sort_values("rating_date").iloc[-1]


def match_historical_ratings(individual_matches, ratings):
    """Attach each player's latest rating dated strictly before the match date."""
    matches = individual_matches.copy()
    matches["match_date"] = pd.to_datetime(matches["match_date"]).dt.normalize()
    ratings = ratings.copy().sort_values(["rating_date", "player_id"])

    def attach(side):
        player_column = f"{side}_player_id"
        left = matches[["individual_match_id", "match_date", player_column]].rename(
            columns={player_column: "player_id"}
        ).sort_values(["match_date", "player_id"])
        joined = pd.merge_asof(
            left, ratings[["player_id", "rating_date", "rating"]],
            left_on="match_date", right_on="rating_date", by="player_id",
            direction="backward", allow_exact_matches=False,
        )
        joined["rating_age_days"] = (
            joined["match_date"] - joined["rating_date"]
        ).dt.days
        return joined.set_index("individual_match_id")[[
            "rating_date", "rating", "rating_age_days"
        ]].add_prefix(f"{side}_")

    result = matches.set_index("individual_match_id")
    result = result.join(attach("home")).join(attach("away"))
    result["rating_difference_home"] = result["home_rating"] - result["away_rating"]
    result["both_ratings_available"] = result[["home_rating", "away_rating"]].notna().all(axis=1)
    return result.reset_index()

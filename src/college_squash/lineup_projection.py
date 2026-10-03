from bisect import bisect_left
from collections import defaultdict

import pandas as pd


def most_recent_lineup(history):
    """Return the last observed lineup, or None when the team has no prior lineup."""
    return list(history[-1]) if history else None


def recent_consensus_lineup(history, window=5):
    """Choose frequent recent starters and order them by their typical position."""
    recent = history[-window:]
    if not recent:
        return None
    appearances = defaultdict(list)
    for lineup_number, lineup in enumerate(recent):
        for position, player_id in enumerate(lineup, start=1):
            appearances[player_id].append((lineup_number, position))
    ranked_players = sorted(
        appearances,
        key=lambda player_id: (
            -len(appearances[player_id]),
            -max(item[0] for item in appearances[player_id]),
            player_id,
        ),
    )[:9]
    if len(ranked_players) < 9:
        return None

    def order(player_id):
        positions = [item[1] for item in appearances[player_id]]
        latest_position = appearances[player_id][-1][1]
        return (float(pd.Series(positions).median()), latest_position, player_id)

    return sorted(ranked_players, key=order)


def lineup_confidence(history, projected, window=5):
    """Summarize recent participation and position stability on a zero-to-one scale."""
    if not history or not projected:
        return 0.0
    recent = history[-window:]
    participation, position_stability = [], []
    for expected_position, player_id in enumerate(projected, start=1):
        observed_positions = [
            position
            for lineup in recent
            for position, observed_player in enumerate(lineup, start=1)
            if observed_player == player_id
        ]
        participation.append(len(observed_positions) / len(recent))
        position_stability.append(
            observed_positions.count(expected_position) / len(observed_positions)
            if observed_positions else 0.0
        )
    stability = (sum(participation) + sum(position_stability)) / 18
    evidence = min(len(recent) / 3, 1.0)
    return float(stability * evidence)


def lineup_agreement(projected, actual):
    if not projected or not actual:
        return {"correct_players": 0, "correct_positions": 0, "all_players_correct": False}
    return {
        "correct_players": len(set(projected) & set(actual)),
        "correct_positions": sum(a == b for a, b in zip(projected, actual)),
        "all_players_correct": set(projected) == set(actual),
    }


def build_historical_projections(lineup_rows):
    """Project each lineup from earlier dates only; updates are batched by date."""
    frame = lineup_rows.copy()
    frame["match_date"] = pd.to_datetime(frame["match_date"])
    history = defaultdict(list)
    output = []
    for match_date, day in frame.sort_values(
        ["match_date", "source_match_id", "side", "position"]
    ).groupby("match_date", sort=True):
        actual_by_team = []
        for (source_match_id, season, side, program_id), group in day.groupby(
            ["source_match_id", "season", "side", "program_id"], sort=False
        ):
            actual = group.sort_values("position")["player_id"].astype(int).tolist()
            if len(actual) != 9:
                continue
            history_key = (int(program_id), season)
            previous = history[history_key]
            recent = most_recent_lineup(previous)
            consensus = recent_consensus_lineup(previous)
            for method, projected in {"most_recent": recent, "recent_consensus": consensus}.items():
                agreement = lineup_agreement(projected, actual)
                output.append({
                    "source_match_id": int(source_match_id), "match_date": match_date,
                    "side": side, "program_id": int(program_id), "method": method,
                    "projected_lineup": projected, "actual_lineup": actual,
                    "prior_complete_lineups": len(previous),
                    "confidence": lineup_confidence(previous, projected),
                    **agreement,
                })
            actual_by_team.append((history_key, actual))
        # Nothing played on this date can affect another projection on the same date.
        for history_key, actual in actual_by_team:
            history[history_key].append(actual)
    return pd.DataFrame(output)


def rating_lookup(ratings):
    lookup = {}
    frame = ratings.copy()
    frame["rating_date"] = pd.to_datetime(frame["rating_date"])
    for player_id, group in frame.sort_values("rating_date").groupby("player_id"):
        lookup[int(player_id)] = (
            group["rating_date"].tolist(), group["rating"].astype(float).tolist()
        )
    return lookup


def rating_before(lookup, player_id, match_date):
    history = lookup.get(int(player_id))
    if not history:
        return None
    dates, values = history
    index = bisect_left(dates, pd.Timestamp(match_date)) - 1
    return values[index] if index >= 0 else None

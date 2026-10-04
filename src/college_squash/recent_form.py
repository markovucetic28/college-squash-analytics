"""Descriptive recent-form labels; these values never enter match predictions."""

from collections import defaultdict

import numpy as np
import pandas as pd


FORM_THRESHOLD = 0.10
MINIMUM_MATCHES = 3
FORM_WINDOW = 5

FORM_COPY = {
    "above": {
        "label": "Above expectations",
        "description": "Recent results have been stronger than expected based on opponent ratings.",
    },
    "expected": {
        "label": "As expected",
        "description": "Recent results are broadly consistent with the player’s rating.",
    },
    "below": {
        "label": "Below expectations",
        "description": "Recent results have been weaker than expected based on opponent ratings.",
    },
    "limited": {
        "label": "Limited recent data",
        "description": "Not enough recent rated matches to assess form.",
    },
}


def classify_recent_form(residuals, minimum_matches=MINIMUM_MATCHES, threshold=FORM_THRESHOLD):
    """Classify recent performance versus pre-match rating expectations."""
    values = [float(value) for value in residuals if pd.notna(value)]
    if len(values) < minimum_matches:
        state = "limited"
        score = None
    else:
        score = float(np.mean(values[-FORM_WINDOW:]))
        state = "above" if score >= threshold else "below" if score <= -threshold else "expected"
    return {"state": state, "score": score, "matches": len(values), **FORM_COPY[state]}


def recent_form_by_player(connection, artifact, player_ids, as_of_date=None):
    """Calculate all requested players together to avoid per-player database calls."""
    ids = sorted({int(player_id) for player_id in player_ids if pd.notna(player_id)})
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    date_clause = " AND m.match_date < ?" if as_of_date else ""
    params = [*ids, *ids]
    if as_of_date:
        params.append(str(as_of_date))
    rows = pd.read_sql_query(f"""
        SELECT im.individual_match_id, m.match_date, im.position,
               im.home_player_id, im.away_player_id, im.winner_side,
               ratings.home_rating, ratings.away_rating,
               ratings.home_rating_date, ratings.away_rating_date
        FROM individual_matches im
        JOIN matches m USING(source_match_id)
        JOIN individual_match_ratings ratings USING(individual_match_id)
        WHERE (im.home_player_id IN ({placeholders}) OR im.away_player_id IN ({placeholders}))
          AND ratings.home_rating IS NOT NULL AND ratings.away_rating IS NOT NULL
          AND ratings.home_rating_date < m.match_date
          AND ratings.away_rating_date < m.match_date
          {date_clause}
        ORDER BY m.match_date, im.individual_match_id
    """, connection, params=params)

    histories = defaultdict(list)
    if not rows.empty:
        features = pd.DataFrame({
            "official_rating_diff": rows["home_rating"] - rows["away_rating"],
            "position": rows["position"],
        })
        model = artifact["model"] if isinstance(artifact, dict) else artifact
        columns = artifact.get("features", ["official_rating_diff", "position"]) if isinstance(artifact, dict) else ["official_rating_diff", "position"]
        home_probabilities = model.predict_proba(features[columns])[:, 1]
        for row, home_probability in zip(rows.itertuples(index=False), home_probabilities):
            if row.home_player_id in ids:
                histories[row.home_player_id].append(int(row.winner_side == "H") - home_probability)
            if row.away_player_id in ids:
                histories[row.away_player_id].append(int(row.winner_side == "V") - (1-home_probability))
    return {player_id: classify_recent_form(histories[player_id]) for player_id in ids}

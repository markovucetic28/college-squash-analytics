import sqlite3

import numpy as np
import pandas as pd

from college_squash.recent_form import classify_recent_form, recent_form_by_player


class FixedModel:
    def predict_proba(self, features):
        probability = np.full(len(features), .6)
        return np.column_stack([1-probability, probability])


def test_recent_form_classification_and_minimum_history():
    assert classify_recent_form([.4, .3])["state"] == "limited"
    assert classify_recent_form([.2, .1, .3])["state"] == "above"
    assert classify_recent_form([-.2, -.1, -.3])["state"] == "below"
    assert classify_recent_form([-.05, .02, .01])["state"] == "expected"


def test_recent_form_uses_only_strictly_pre_match_ratings_and_cutoff():
    connection = sqlite3.connect(":memory:")
    connection.executescript("""
        CREATE TABLE matches (source_match_id INTEGER PRIMARY KEY, match_date TEXT);
        CREATE TABLE individual_matches (
          individual_match_id INTEGER PRIMARY KEY, source_match_id INTEGER,
          position INTEGER, home_player_id INTEGER, away_player_id INTEGER, winner_side TEXT
        );
        CREATE TABLE individual_match_ratings (
          individual_match_id INTEGER PRIMARY KEY, home_rating REAL, away_rating REAL,
          home_rating_date TEXT, away_rating_date TEXT
        );
        INSERT INTO matches VALUES (1,'2025-01-02'),(2,'2025-01-03'),(3,'2025-01-04'),(4,'2025-01-05');
        INSERT INTO individual_matches VALUES
          (1,1,1,10,20,'H'),(2,2,1,10,21,'H'),(3,3,1,10,22,'H'),(4,4,1,10,23,'H');
        INSERT INTO individual_match_ratings VALUES
          (1,5,5,'2025-01-01','2025-01-01'),
          (2,5,5,'2025-01-03','2025-01-02'),
          (3,5,5,'2025-01-02','2025-01-02'),
          (4,5,5,'2025-01-02','2025-01-02');
    """)
    artifact = {"model": FixedModel(), "features": ["official_rating_diff", "position"]}
    result = recent_form_by_player(connection, artifact, [10], as_of_date="2025-01-05")[10]
    # Match 2 is excluded because its home rating is same-day; match 4 is after the cutoff.
    assert result["matches"] == 2
    assert result["state"] == "limited"


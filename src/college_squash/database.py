import json
import os
import sqlite3
from pathlib import Path

import pandas as pd

from college_squash.clublocker import SEASONS, load_all_divisions, normalize_team_name
from college_squash.current_season import load_current_schedule
from college_squash.players import load_player_dataset, roster_identities
from college_squash.preseason import sync_current_rosters
from college_squash.ratings import load_rating_histories, match_historical_ratings
from college_squash.live_season import LIVE_SCHEMA


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE sources (
    source_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    results_url TEXT NOT NULL,
    data_url TEXT NOT NULL,
    retrieved_at_utc TEXT NOT NULL
);

CREATE TABLE divisions (
    division_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    gender TEXT NOT NULL CHECK (gender IN ('men', 'women')),
    season TEXT NOT NULL,
    source_id INTEGER NOT NULL REFERENCES sources(source_id),
    UNIQUE (gender, season)
);

CREATE TABLE programs (
    program_id INTEGER PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    gender TEXT NOT NULL CHECK (gender IN ('men', 'women')),
    UNIQUE (canonical_name, gender)
);

CREATE TABLE teams (
    team_id INTEGER NOT NULL,
    division_id INTEGER NOT NULL REFERENCES divisions(division_id),
    program_id INTEGER NOT NULL REFERENCES programs(program_id),
    name TEXT NOT NULL,
    source_name TEXT NOT NULL,
    is_varsity INTEGER NOT NULL CHECK (is_varsity IN (0, 1)),
    PRIMARY KEY (team_id, division_id),
    UNIQUE (program_id, division_id)
);

CREATE TABLE matches (
    source_match_id INTEGER PRIMARY KEY,
    division_id INTEGER NOT NULL REFERENCES divisions(division_id),
    match_date TEXT NOT NULL,
    season TEXT NOT NULL,
    home_team_id INTEGER NOT NULL,
    away_team_id INTEGER NOT NULL,
    home_score INTEGER NOT NULL CHECK (home_score >= 0),
    away_score INTEGER NOT NULL CHECK (away_score >= 0),
    match_time TEXT,
    venue_name TEXT,
    FOREIGN KEY (home_team_id, division_id) REFERENCES teams(team_id, division_id),
    FOREIGN KEY (away_team_id, division_id) REFERENCES teams(team_id, division_id),
    CHECK (home_score != away_score),
    UNIQUE (match_date, division_id, home_team_id, away_team_id, match_time)
);

CREATE INDEX matches_home_team_index ON matches (division_id, home_team_id, match_date);
CREATE INDEX matches_away_team_index ON matches (division_id, away_team_id, match_date);
CREATE INDEX matches_season_index ON matches (season, division_id, match_date);
CREATE INDEX teams_program_index ON teams (program_id, division_id);

CREATE TABLE players (
    player_id INTEGER PRIMARY KEY,
    display_name TEXT,
    identity_source TEXT NOT NULL
);

CREATE TABLE player_team_seasons (
    player_id INTEGER NOT NULL REFERENCES players(player_id),
    division_id INTEGER NOT NULL,
    team_id INTEGER NOT NULL,
    roster_position TEXT,
    source_url TEXT NOT NULL,
    PRIMARY KEY (player_id, division_id, team_id),
    FOREIGN KEY (team_id, division_id) REFERENCES teams(team_id, division_id)
);

CREATE TABLE individual_matches (
    individual_match_id INTEGER PRIMARY KEY,
    source_match_id INTEGER NOT NULL REFERENCES matches(source_match_id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position BETWEEN 1 AND 9),
    home_player_id INTEGER NOT NULL REFERENCES players(player_id),
    away_player_id INTEGER NOT NULL REFERENCES players(player_id),
    winner_side TEXT NOT NULL CHECK (winner_side IN ('H', 'V')),
    winner_player_id INTEGER NOT NULL REFERENCES players(player_id),
    loser_player_id INTEGER NOT NULL REFERENCES players(player_id),
    game_scores_winner_first TEXT NOT NULL,
    source_url TEXT NOT NULL,
    UNIQUE (source_match_id, position)
);

CREATE INDEX individual_matches_team_match_index ON individual_matches (source_match_id);
CREATE INDEX individual_matches_home_player_index ON individual_matches (home_player_id);
CREATE INDEX individual_matches_away_player_index ON individual_matches (away_player_id);

CREATE TABLE player_ratings (
    player_id INTEGER NOT NULL REFERENCES players(player_id),
    rating_date TEXT NOT NULL,
    rating REAL NOT NULL CHECK (rating > 0),
    season TEXT NOT NULL,
    ranking_group_id INTEGER NOT NULL,
    rating_group TEXT,
    division_id INTEGER,
    source_season TEXT,
    source_url TEXT NOT NULL,
    retrieved_at_utc TEXT NOT NULL,
    PRIMARY KEY (player_id, rating_date)
);

CREATE TABLE individual_match_ratings (
    individual_match_id INTEGER PRIMARY KEY REFERENCES individual_matches(individual_match_id)
        ON DELETE CASCADE,
    home_rating_date TEXT,
    home_rating REAL,
    home_rating_age_days INTEGER,
    away_rating_date TEXT,
    away_rating REAL,
    away_rating_age_days INTEGER,
    rating_difference_home REAL,
    both_ratings_available INTEGER NOT NULL CHECK (both_ratings_available IN (0, 1)),
    CHECK (home_rating_date IS NULL OR home_rating_age_days > 0),
    CHECK (away_rating_date IS NULL OR away_rating_age_days > 0)
);

CREATE TABLE scheduled_matches (
    source_match_id INTEGER PRIMARY KEY,
    season TEXT NOT NULL,
    gender TEXT NOT NULL CHECK (gender IN ('men', 'women')),
    division_id INTEGER NOT NULL,
    match_date TEXT NOT NULL,
    match_time TEXT,
    home_team_id INTEGER NOT NULL,
    home_team TEXT NOT NULL,
    away_team_id INTEGER NOT NULL,
    away_team TEXT NOT NULL,
    venue_name TEXT,
    status TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_data_url TEXT NOT NULL,
    retrieved_at_utc TEXT
);

CREATE INDEX scheduled_matches_date_index
ON scheduled_matches (match_date, gender);
"""

SCHEMA += LIVE_SCHEMA


def connect_database(database_path, read_only=False):
    if read_only:
        database_uri = f"file:{Path(database_path).resolve()}?mode=ro"
        connection = sqlite3.connect(database_uri, uri=True)
    else:
        connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _metadata(raw_directory, season, gender):
    path = Path(raw_directory) / f"csa_{gender}_varsity_{season}.metadata.json"
    return json.loads(path.read_text(encoding="utf-8"))


def build_database(raw_directory, database_path):
    """Rebuild SQLite from all validated source snapshots."""
    database_path = Path(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = database_path.with_suffix(database_path.suffix + ".tmp")
    temporary_path.unlink(missing_ok=True)
    matches, exclusions, varsity_teams = load_all_divisions(raw_directory)
    individual_matches, player_exclusions = load_player_dataset(raw_directory, matches)
    ratings, rating_exclusions = load_rating_histories(raw_directory)
    scheduled_matches, scheduled_exclusions = load_current_schedule(raw_directory)

    division_rows, source_rows = [], []
    for season, divisions in SEASONS.items():
        for gender, division_id in divisions.items():
            metadata = _metadata(raw_directory, season, gender)
            source_rows.append((division_id, "College Squash Association / Club Locker",
                                metadata["schedule_source_url"], metadata["schedule_data_url"],
                                metadata["retrieved_at_utc"]))
            division_rows.append((division_id, f"CSA {gender.title()}'s Varsity",
                                  gender, season, division_id))

    team_details = {}
    varsity_keys = set()
    for team in varsity_teams.itertuples(index=False):
        key = (int(team.division_id), int(team.team_id))
        varsity_keys.add(key)
        team_details[key] = (team.team_name, team.source_team_name)
    for match in matches.itertuples(index=False):
        for team_id, canonical_name in [
            (match.home_team_id, match.home_team), (match.away_team_id, match.away_team)
        ]:
            key = (int(match.division_id), int(team_id))
            team_details.setdefault(key, (canonical_name, canonical_name))

    gender_by_division = {
        division_id: gender for divisions in SEASONS.values()
        for gender, division_id in divisions.items()
    }
    program_keys = sorted({
        (normalize_team_name(canonical_name), gender_by_division[division_id])
        for (division_id, _), (canonical_name, _) in team_details.items()
    }, key=lambda item: (item[1], item[0]))
    program_ids = {key: number for number, key in enumerate(program_keys, start=1)}
    program_rows = [(number, name, gender) for (name, gender), number in program_ids.items()]
    team_rows = []
    for (division_id, team_id), (canonical_name, source_name) in sorted(team_details.items()):
        gender = gender_by_division[division_id]
        name = normalize_team_name(canonical_name)
        team_rows.append((team_id, division_id, program_ids[(name, gender)], name,
                          source_name, int((division_id, team_id) in varsity_keys)))

    connection = connect_database(temporary_path)
    try:
        connection.executescript(SCHEMA)
        current_roster_count = sync_current_rosters(connection, raw_directory)
        connection.executemany("INSERT INTO sources VALUES (?, ?, ?, ?, ?)", source_rows)
        connection.executemany("INSERT INTO divisions VALUES (?, ?, ?, ?, ?)", division_rows)
        connection.executemany("INSERT INTO programs VALUES (?, ?, ?)", program_rows)
        connection.executemany("INSERT INTO teams VALUES (?, ?, ?, ?, ?, ?)", team_rows)
        if not scheduled_matches.empty:
            connection.executemany(
                "INSERT INTO scheduled_matches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [tuple(row) for row in scheduled_matches[[
                    "source_match_id", "season", "gender", "division_id", "match_date",
                    "match_time", "home_team_id", "home_team", "away_team_id", "away_team",
                    "venue_name", "status", "source_url", "source_data_url", "retrieved_at_utc",
                ]].itertuples(index=False, name=None)],
            )
        connection.executemany(
            "INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(int(m.source_id), int(m.division_id), m.date.strftime("%Y-%m-%d"), m.season,
              int(m.home_team_id), int(m.away_team_id), int(m.home_score), int(m.away_score),
              m.match_time, m.venue_name) for m in matches.itertuples(index=False)],
        )
        identities, memberships = {}, {}
        roster_directory = Path(raw_directory) / "player_rosters"
        for roster_path in sorted(roster_directory.glob("*.json")):
            division_id, team_id = map(int, roster_path.stem.split("_", 1))
            roster_rows = json.loads(roster_path.read_text(encoding="utf-8"))
            roster_players, roster_memberships = roster_identities(
                roster_rows, division_id, team_id
            )
            for player in roster_players:
                if player["display_name"]:
                    identities[player["player_id"]] = player["display_name"]
            for membership in roster_memberships:
                memberships[(membership["player_id"], division_id, team_id)] = membership
        if not individual_matches.empty:
            match_player_ids = set(individual_matches["home_player_id"]) | set(
                individual_matches["away_player_id"]
            )
            player_rows = [
                (int(player_id), identities.get(player_id),
                 "official_roster" if identities.get(player_id) else "official_scorecard_id")
                for player_id in sorted(match_player_ids | set(identities))
            ]
            connection.executemany("INSERT INTO players VALUES (?, ?, ?)", player_rows)
            valid_team_keys = set(team_details)
            membership_rows = [
                (int(item["player_id"]), int(item["division_id"]), int(item["team_id"]),
                 item["roster_position"], item["source_url"])
                for item in memberships.values()
                if (int(item["division_id"]), int(item["team_id"])) in valid_team_keys
                and int(item["player_id"]) in match_player_ids
            ]
            connection.executemany(
                "INSERT INTO player_team_seasons VALUES (?, ?, ?, ?, ?)", membership_rows
            )
            connection.executemany(
                "INSERT INTO individual_matches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [tuple(row) for row in individual_matches[[
                    "individual_match_id", "source_match_id", "position", "home_player_id",
                    "away_player_id", "winner_side", "winner_player_id", "loser_player_id",
                    "game_scores_winner_first", "source_url",
                ]].itertuples(index=False, name=None)],
            )
            if not ratings.empty:
                connection.executemany(
                    "INSERT INTO player_ratings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (int(row.player_id), row.rating_date.strftime("%Y-%m-%d"),
                         float(row.rating), row.season, int(row.ranking_group_id),
                         row.rating_group, int(row.division_id), row.source_season,
                         row.source_url, row.retrieved_at_utc)
                        for row in ratings.itertuples(index=False)
                    ],
                )
                match_dates = matches[["source_id", "date"]].rename(columns={
                    "source_id": "source_match_id", "date": "match_date"
                })
                rating_input = individual_matches.merge(match_dates, on="source_match_id")
                mapped = match_historical_ratings(rating_input, ratings)
                connection.executemany(
                    "INSERT INTO individual_match_ratings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (int(row.individual_match_id),
                         None if pd.isna(row.home_rating_date) else row.home_rating_date.strftime("%Y-%m-%d"),
                         None if pd.isna(row.home_rating) else float(row.home_rating),
                         None if pd.isna(row.home_rating_age_days) else int(row.home_rating_age_days),
                         None if pd.isna(row.away_rating_date) else row.away_rating_date.strftime("%Y-%m-%d"),
                         None if pd.isna(row.away_rating) else float(row.away_rating),
                         None if pd.isna(row.away_rating_age_days) else int(row.away_rating_age_days),
                         None if pd.isna(row.rating_difference_home) else float(row.rating_difference_home),
                         int(row.both_ratings_available))
                        for row in mapped.itertuples(index=False)
                    ],
                )
        connection.commit()
        errors = connection.execute("PRAGMA foreign_key_check").fetchall()
        if errors:
            raise ValueError(f"Foreign key validation failed: {errors}")
    except Exception:
        connection.close()
        temporary_path.unlink(missing_ok=True)
        raise
    else:
        connection.close()
    os.replace(temporary_path, database_path)
    return {"sources": len(source_rows), "divisions": len(division_rows),
            "programs": len(program_rows), "teams": len(team_rows),
            "varsity_teams": len(varsity_teams), "matches": len(matches),
            "exclusions": len(exclusions), "players": len(identities),
            "individual_matches": len(individual_matches),
            "player_exclusions": len(player_exclusions), "ratings": len(ratings),
            "rating_exclusions": len(rating_exclusions),
            "scheduled_matches": len(scheduled_matches),
            "scheduled_exclusions": len(scheduled_exclusions),
            "current_roster_players": current_roster_count}

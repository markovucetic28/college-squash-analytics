import re
import unicodedata

import pandas as pd


def available_seasons(connection, gender=None):
    query = "SELECT DISTINCT season FROM divisions"
    params = ()
    if gender:
        query += " WHERE gender = ?"
        params = (gender,)
    rows = connection.execute(query, params).fetchall()
    return sorted((row["season"] for row in rows), reverse=True)


def _find_program(connection, team_name, gender):
    row = connection.execute(
        "SELECT program_id, canonical_name, gender FROM programs WHERE canonical_name = ? AND gender = ?",
        (team_name, gender),
    ).fetchone()
    if row is None:
        raise ValueError(f"Unknown {gender}'s varsity team: {team_name}")
    return row


def varsity_team_names(connection, gender, season=None):
    query = """
        SELECT DISTINCT p.canonical_name
        FROM programs p
        JOIN teams t ON t.program_id = p.program_id
        JOIN divisions d ON d.division_id = t.division_id
        WHERE p.gender = ? AND t.is_varsity = 1
    """
    params = [gender]
    if season:
        query += " AND d.season = ?"
        params.append(season)
    query += " ORDER BY p.canonical_name"
    return [row["canonical_name"] for row in connection.execute(query, params)]


def season_history(connection, team_name, gender, season=None):
    program = _find_program(connection, team_name, gender)
    query = """
        SELECT m.source_match_id, m.match_date AS date, m.season,
               opponent_program.canonical_name AS opponent,
               CASE WHEN home.program_id = ? THEN m.home_score ELSE m.away_score END AS team_score,
               CASE WHEN home.program_id = ? THEN m.away_score ELSE m.home_score END AS opponent_score,
               CASE WHEN (home.program_id = ? AND m.home_score > m.away_score)
                       OR (away.program_id = ? AND m.away_score > m.home_score)
                    THEN 'W' ELSE 'L' END AS result,
               m.venue_name, s.results_url AS source_url
        FROM matches m
        JOIN divisions d ON d.division_id = m.division_id
        JOIN sources s ON s.source_id = d.source_id
        JOIN teams home ON home.division_id = m.division_id AND home.team_id = m.home_team_id
        JOIN teams away ON away.division_id = m.division_id AND away.team_id = m.away_team_id
        JOIN programs opponent_program ON opponent_program.program_id =
            CASE WHEN home.program_id = ? THEN away.program_id ELSE home.program_id END
        WHERE d.gender = ? AND (home.program_id = ? OR away.program_id = ?)
    """
    params = [program["program_id"]] * 5 + [gender, program["program_id"], program["program_id"]]
    if season:
        query += " AND m.season = ?"
        params.append(season)
    query += " ORDER BY m.match_date, m.source_match_id"
    history = pd.read_sql_query(query, connection, params=params)
    if not history.empty:
        history["date"] = pd.to_datetime(history["date"])
        history["margin"] = history["team_score"] - history["opponent_score"]
    return history


def team_summary(connection, team_name, gender, season=None, recent_matches=5):
    if recent_matches < 1:
        raise ValueError("recent_matches must be at least 1")
    history = season_history(connection, team_name, gender, season)
    if history.empty:
        raise ValueError(f"No {gender}'s matches found for {team_name}")
    wins = int((history["result"] == "W").sum())
    total = len(history)
    return {
        "team": team_name, "gender": gender, "season": season,
        "wins": wins, "losses": total - wins, "total_matches": total,
        "win_percentage": wins / total,
        "recent_form": "".join(history.tail(recent_matches)["result"]),
        "average_team_score": float(history["team_score"].mean()),
        "average_opponent_score": float(history["opponent_score"].mean()),
        "average_margin": float(history["margin"].mean()),
    }


def _season_win_percentages(connection, gender, season):
    rows = connection.execute(
        """
        SELECT home.program_id home_id, away.program_id away_id, m.home_score, m.away_score
        FROM matches m JOIN divisions d ON d.division_id=m.division_id
        JOIN teams home ON home.division_id=m.division_id AND home.team_id=m.home_team_id
        JOIN teams away ON away.division_id=m.division_id AND away.team_id=m.away_team_id
        WHERE d.gender=? AND m.season=?
        """, (gender, season)
    ).fetchall()
    records = {}
    for row in rows:
        for key, won in [(row["home_id"], row["home_score"] > row["away_score"]),
                         (row["away_id"], row["away_score"] > row["home_score"])]:
            records.setdefault(key, [0, 0])
            records[key][0] += int(won)
            records[key][1] += 1
    return {key: wins / total for key, (wins, total) in records.items()}


def strength_of_schedule(connection, team_name, gender, season=None):
    if season is None:
        seasons = [row["season"] for row in connection.execute(
            """SELECT DISTINCT m.season FROM matches m JOIN divisions d USING(division_id)
               WHERE d.gender=? ORDER BY m.season""", (gender,))]
        weighted, count = 0.0, 0
        for item in seasons:
            history = season_history(connection, team_name, gender, item)
            if not history.empty:
                weighted += strength_of_schedule(connection, team_name, gender, item) * len(history)
                count += len(history)
        if not count:
            raise ValueError(f"No {gender}'s matches found for {team_name}")
        return weighted / count

    program = _find_program(connection, team_name, gender)
    rows = connection.execute(
        """
        SELECT CASE WHEN home.program_id=? THEN away.program_id ELSE home.program_id END opponent_id
        FROM matches m JOIN divisions d ON d.division_id=m.division_id
        JOIN teams home ON home.division_id=m.division_id AND home.team_id=m.home_team_id
        JOIN teams away ON away.division_id=m.division_id AND away.team_id=m.away_team_id
        WHERE d.gender=? AND m.season=? AND (home.program_id=? OR away.program_id=?)
        """, (program["program_id"], gender, season, program["program_id"], program["program_id"])
    ).fetchall()
    if not rows:
        raise ValueError(f"No {season} matches found for {team_name}")
    percentages = _season_win_percentages(connection, gender, season)
    return sum(percentages[row["opponent_id"]] for row in rows) / len(rows)


def season_by_season_summary(connection, team_name, gender):
    rows = []
    for season in reversed(available_seasons(connection, gender)):
        history = season_history(connection, team_name, gender, season)
        if history.empty:
            continue
        summary = team_summary(connection, team_name, gender, season)
        rows.append({"season": season, "wins": summary["wins"], "losses": summary["losses"],
                     "win_percentage": summary["win_percentage"],
                     "average_margin": summary["average_margin"],
                     "strength_of_schedule": strength_of_schedule(connection, team_name, gender, season)})
    return pd.DataFrame(rows)


def performance_trend(connection, team_name, gender, season=None, rolling_matches=5):
    if rolling_matches < 1:
        raise ValueError("rolling_matches must be at least 1")
    history = season_history(connection, team_name, gender, season).copy()
    history["match_number"] = range(1, len(history) + 1)
    history["cumulative_wins"] = (history["result"] == "W").cumsum()
    history["cumulative_win_percentage"] = history["cumulative_wins"] / history["match_number"]
    history["rolling_average_margin"] = history["margin"].rolling(rolling_matches, min_periods=1).mean()
    return history[["date", "match_number", "cumulative_wins",
                    "cumulative_win_percentage", "rolling_average_margin"]]


def division_rankings(connection, gender, season=None):
    season = season or available_seasons(connection, gender)[0]
    rows = []
    for name in varsity_team_names(connection, gender, season):
        summary = team_summary(connection, name, gender, season)
        rows.append({"team": name, "wins": summary["wins"], "losses": summary["losses"],
                     "win_percentage": summary["win_percentage"],
                     "strength_of_schedule": strength_of_schedule(connection, name, gender, season),
                     "average_margin": summary["average_margin"],
                     "recent_form": summary["recent_form"]})
    rankings = pd.DataFrame(rows).sort_values(
        ["win_percentage", "strength_of_schedule", "average_margin", "team"],
        ascending=[False, False, False, True])
    rankings.insert(0, "rank", range(1, len(rankings) + 1))
    return rankings.reset_index(drop=True)


def head_to_head(connection, team_one, team_two, gender, season=None):
    first = _find_program(connection, team_one, gender)
    second = _find_program(connection, team_two, gender)
    query = """
        SELECT home.program_id home_id, away.program_id away_id, m.home_score, m.away_score
        FROM matches m JOIN divisions d ON d.division_id=m.division_id
        JOIN teams home ON home.division_id=m.division_id AND home.team_id=m.home_team_id
        JOIN teams away ON away.division_id=m.division_id AND away.team_id=m.away_team_id
        WHERE d.gender=? AND ((home.program_id=? AND away.program_id=?)
                           OR (home.program_id=? AND away.program_id=?))
    """
    params = [gender, first["program_id"], second["program_id"],
              second["program_id"], first["program_id"]]
    if season:
        query += " AND m.season=?"
        params.append(season)
    rows = connection.execute(query, params).fetchall()
    first_wins = sum((r["home_id"] == first["program_id"] and r["home_score"] > r["away_score"])
                     or (r["away_id"] == first["program_id"] and r["away_score"] > r["home_score"])
                     for r in rows)
    return {"team_one": team_one, "team_two": team_two, "matches": len(rows),
            "team_one_wins": first_wins, "team_two_wins": len(rows) - first_wins}


def scheduled_matches(connection, gender=None, team_name=None, start_date=None, end_date=None):
    """Return the current schedule, including clean live status transitions."""
    live_count = connection.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='live_matches'"
    ).fetchone()[0]
    table = "live_matches" if live_count and connection.execute(
        "SELECT COUNT(*) FROM live_matches"
    ).fetchone()[0] else "scheduled_matches"
    query = f"SELECT * FROM {table} WHERE 1=1"
    params = []
    if gender:
        query += " AND gender = ?"
        params.append(gender)
    if team_name:
        query += " AND (home_team = ? OR away_team = ?)"
        params.extend([team_name, team_name])
    if start_date:
        query += " AND match_date >= ?"
        params.append(str(start_date))
    if end_date:
        query += " AND match_date <= ?"
        params.append(str(end_date))
    query += " ORDER BY match_date, COALESCE(match_time, ''), source_match_id"
    return pd.read_sql_query(query, connection, params=params)


def head_to_head_history(connection, team_one, team_two, gender):
    """Return every verified meeting from team one's perspective."""
    first = _find_program(connection, team_one, gender)
    second = _find_program(connection, team_two, gender)
    query = """
        SELECT m.match_date AS date, m.season,
               CASE WHEN home.program_id=? THEN m.home_score ELSE m.away_score END team_score,
               CASE WHEN home.program_id=? THEN m.away_score ELSE m.home_score END opponent_score,
               CASE WHEN (home.program_id=? AND m.home_score>m.away_score)
                         OR (away.program_id=? AND m.away_score>m.home_score)
                    THEN 'W' ELSE 'L' END result,
               m.venue_name
        FROM matches m JOIN divisions d ON d.division_id=m.division_id
        JOIN teams home ON home.division_id=m.division_id AND home.team_id=m.home_team_id
        JOIN teams away ON away.division_id=m.division_id AND away.team_id=m.away_team_id
        WHERE d.gender=? AND ((home.program_id=? AND away.program_id=?)
                           OR (home.program_id=? AND away.program_id=?))
        ORDER BY m.match_date DESC, m.source_match_id DESC
    """
    params = [first["program_id"]] * 4 + [gender, first["program_id"],
              second["program_id"], second["program_id"], first["program_id"]]
    history = pd.read_sql_query(query, connection, params=params)
    if not history.empty:
        history["date"] = pd.to_datetime(history["date"])
    return history


def player_search(connection, search_text="", limit=100):
    """Search current and historical identities with normalized, token-aware matching."""
    if not search_text.strip():
        return pd.DataFrame(columns=[
            "player_id", "display_name", "canonical_team_name",
            "gender", "season", "is_current",
        ])
    query = """
        WITH historical AS (
            SELECT p.player_id, p.display_name,
                   program.canonical_name canonical_team_name,
                   d.gender, d.season,
                   ROW_NUMBER() OVER (PARTITION BY p.player_id ORDER BY d.season DESC) row_number
            FROM players p
            JOIN player_team_seasons pts USING(player_id)
            JOIN divisions d USING(division_id)
            JOIN teams t ON t.division_id=pts.division_id AND t.team_id=pts.team_id
            JOIN programs program USING(program_id)
        ), candidates AS (
            SELECT player_id, display_name,
                   team_name canonical_team_name, gender, season, 1 is_current
            FROM current_roster_players
            UNION ALL
            SELECT player_id, display_name, canonical_team_name,
                   gender, season, 0 is_current
            FROM historical
            WHERE row_number=1 AND NOT EXISTS (
                SELECT 1 FROM current_roster_players cr WHERE cr.player_id=historical.player_id
            )
        )
        SELECT player_id, display_name, canonical_team_name,
               gender, season, MAX(is_current) is_current
        FROM candidates
        WHERE TRIM(display_name) NOT IN ('N/A', ', N/A', '')
          AND display_name NOT LIKE ',%'
        GROUP BY player_id, display_name
        ORDER BY is_current DESC, display_name
    """
    candidates = pd.read_sql_query(query, connection)
    query_tokens = _search_tokens(search_text)
    scored = []
    for row in candidates.to_dict("records"):
        variants = _name_search_variants(row["display_name"])
        score = max((_search_score(query_tokens, variant) for variant in variants), default=-1)
        if score >= 0:
            row["search_score"] = score
            scored.append(row)
    if not scored:
        return candidates.iloc[0:0]
    return (pd.DataFrame(scored)
            .sort_values(["search_score", "is_current", "display_name"],
                         ascending=[False, False, True])
            .drop(columns="search_score")
            .head(limit)
            .reset_index(drop=True))


def _search_tokens(value):
    ascii_value = unicodedata.normalize("NFKD", str(value))
    ascii_value = "".join(character for character in ascii_value
                          if not unicodedata.combining(character))
    return re.findall(r"[a-z0-9]+", ascii_value.lower())


def _name_search_variants(display_name):
    variants = [_search_tokens(display_name)]
    if "," in display_name:
        last_name, first_names = display_name.split(",", 1)
        variants.append(_search_tokens(f"{first_names} {last_name}"))
    return variants


def _search_score(query_tokens, candidate_tokens):
    if not query_tokens or not candidate_tokens:
        return -1
    if all(any(candidate.startswith(query) for candidate in candidate_tokens)
           for query in query_tokens):
        exact = sum(query in candidate_tokens for query in query_tokens)
        ordered_prefix = int("".join(candidate_tokens).startswith("".join(query_tokens)))
        return 10 + exact + ordered_prefix
    compact_query = "".join(query_tokens)
    compact_candidate = "".join(candidate_tokens)
    return 1 if compact_query in compact_candidate else -1


def player_profile(connection, player_id):
    player = connection.execute(
        "SELECT player_id, display_name FROM players WHERE player_id=?", (int(player_id),)
    ).fetchone()
    if player is None:
        player = connection.execute(
            """SELECT player_id, display_name FROM current_roster_players
               WHERE player_id=? LIMIT 1""", (int(player_id),)
        ).fetchone()
    if player is None:
        raise ValueError("Unknown player")
    memberships = pd.read_sql_query(
        """
        SELECT d.season, d.gender, p.program_id, p.canonical_name team,
               pts.roster_position
        FROM player_team_seasons pts JOIN divisions d USING(division_id)
        JOIN teams t ON t.division_id=pts.division_id AND t.team_id=pts.team_id
        JOIN programs p USING(program_id)
        WHERE pts.player_id=? ORDER BY d.season DESC
        """, connection, params=(int(player_id),)
    )
    matches = pd.read_sql_query(
        """
        SELECT m.match_date date, m.season, im.position,
               CASE WHEN im.home_player_id=? THEN im.away_player_id
                    ELSE im.home_player_id END opponent_player_id,
               CASE WHEN im.home_player_id=? THEN away_player.display_name
                    ELSE home_player.display_name END opponent,
               CASE WHEN im.home_player_id=? THEN away_program.program_id
                    ELSE home_program.program_id END opponent_team_id,
               CASE WHEN im.home_player_id=? THEN away_program.canonical_name
                    ELSE home_program.canonical_name END opponent_team,
               CASE WHEN im.winner_player_id=? THEN 'W' ELSE 'L' END result,
               im.game_scores_winner_first score
        FROM individual_matches im JOIN matches m USING(source_match_id)
        JOIN teams home_team
          ON home_team.division_id=m.division_id AND home_team.team_id=m.home_team_id
        JOIN teams away_team
          ON away_team.division_id=m.division_id AND away_team.team_id=m.away_team_id
        JOIN programs home_program ON home_program.program_id=home_team.program_id
        JOIN programs away_program ON away_program.program_id=away_team.program_id
        JOIN players home_player ON home_player.player_id=im.home_player_id
        JOIN players away_player ON away_player.player_id=im.away_player_id
        WHERE im.home_player_id=? OR im.away_player_id=?
        ORDER BY m.match_date DESC, im.individual_match_id DESC
        """, connection, params=(int(player_id),) * 7
    )
    ratings = pd.read_sql_query(
        """SELECT rating_date date, rating FROM player_ratings
           WHERE player_id=? ORDER BY rating_date""",
        connection, params=(int(player_id),)
    )
    if not matches.empty:
        matches["date"] = pd.to_datetime(matches["date"])
    if not ratings.empty:
        ratings["date"] = pd.to_datetime(ratings["date"])
    return dict(player), memberships, matches, ratings


def recent_lineups(connection, team_name, gender, season="2025-26", limit=3):
    """Return verified lineups only; no prior-season players are projected forward."""
    program = _find_program(connection, team_name, gender)
    query = """
        SELECT m.source_match_id, m.match_date date, m.season, im.position,
               CASE WHEN home.program_id=? THEN hp.display_name ELSE ap.display_name END player,
               opponent.canonical_name opponent
        FROM matches m JOIN divisions d ON d.division_id=m.division_id
        JOIN teams home ON home.division_id=m.division_id AND home.team_id=m.home_team_id
        JOIN teams away ON away.division_id=m.division_id AND away.team_id=m.away_team_id
        JOIN programs opponent ON opponent.program_id=
             CASE WHEN home.program_id=? THEN away.program_id ELSE home.program_id END
        JOIN individual_matches im USING(source_match_id)
        JOIN players hp ON hp.player_id=im.home_player_id
        JOIN players ap ON ap.player_id=im.away_player_id
        WHERE d.gender=? AND m.season=? AND (home.program_id=? OR away.program_id=?)
          AND m.source_match_id IN (
              SELECT m2.source_match_id FROM matches m2
              JOIN divisions d2 ON d2.division_id=m2.division_id
              JOIN teams h2 ON h2.division_id=m2.division_id AND h2.team_id=m2.home_team_id
              JOIN teams a2 ON a2.division_id=m2.division_id AND a2.team_id=m2.away_team_id
              WHERE d2.gender=? AND m2.season=? AND (h2.program_id=? OR a2.program_id=?)
              ORDER BY m2.match_date DESC, m2.source_match_id DESC LIMIT ?)
        ORDER BY m.match_date DESC, m.source_match_id DESC, im.position
    """
    pid = program["program_id"]
    params = (pid, pid, gender, season, pid, pid, gender, season, pid, pid, limit)
    frame = pd.read_sql_query(query, connection, params=params)
    if not frame.empty:
        frame["date"] = pd.to_datetime(frame["date"])
    return frame


def program_elos(connection, gender, season=None, initial=1500.0, k_factor=24.0):
    """Replay verified results chronologically into a descriptive project Elo rating."""
    query = """
        SELECT m.match_date, m.source_match_id, home.program_id home_id,
               away.program_id away_id, m.home_score, m.away_score
        FROM matches m JOIN divisions d ON d.division_id=m.division_id
        JOIN teams home ON home.division_id=m.division_id AND home.team_id=m.home_team_id
        JOIN teams away ON away.division_id=m.division_id AND away.team_id=m.away_team_id
        WHERE d.gender=?
    """
    params = [gender]
    if season:
        query += " AND m.season<=?"
        params.append(season)
    query += " ORDER BY m.match_date, m.source_match_id"
    ratings = {}
    for row in connection.execute(query, params):
        home_rating = ratings.get(row["home_id"], initial)
        away_rating = ratings.get(row["away_id"], initial)
        expected = 1 / (1 + 10 ** ((away_rating - home_rating) / 400))
        outcome = float(row["home_score"] > row["away_score"])
        change = k_factor * (outcome - expected)
        ratings[row["home_id"]] = home_rating + change
        ratings[row["away_id"]] = away_rating - change
    names = connection.execute(
        "SELECT program_id, canonical_name FROM programs WHERE gender=?", (gender,)
    ).fetchall()
    return {row["canonical_name"]: ratings.get(row["program_id"], initial) for row in names}

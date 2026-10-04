"""Prospective shadow evaluation for the frozen simplified two-stage candidate.

This module is not imported by the public prediction API. The live updater calls
it only after source validation to persist append-only, pre-match comparisons.
"""
from collections import defaultdict
from bisect import bisect_left
from datetime import datetime, time, timezone
import hashlib, json
from pathlib import Path
from zoneinfo import ZoneInfo

import joblib
import numpy as np
import pandas as pd

from college_squash.player_model_research import (
    MODEL_FEATURES, exponentially_weighted_mean, score_summary,
)
from college_squash.player_modeling import lineup_score_distribution, probability_at_least_five


SHADOW_VERSION = "simplified-two-stage-v1"
SHADOW_THRESHOLD = .30
SHADOW_ARTIFACT = Path(__file__).resolve().parents[2] / "data/processed/model_stabilization/stabilized_candidate.joblib"
POINT_FEATURES = MODEL_FEATURES["E_point_dominance"]


SHADOW_SCHEMA = """
CREATE TABLE IF NOT EXISTS shadow_prediction_snapshots (
    shadow_snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER NOT NULL,
    generated_at_utc TEXT NOT NULL,
    scheduled_match_date TEXT NOT NULL,
    scheduled_match_time TEXT,
    gender TEXT NOT NULL,
    team_one_id INTEGER NOT NULL,
    team_one_name TEXT NOT NULL,
    team_two_id INTEGER NOT NULL,
    team_two_name TEXT NOT NULL,
    prediction_mode TEXT NOT NULL,
    lineup_confidence REAL,
    production_model_version TEXT NOT NULL,
    production_team_probability REAL NOT NULL,
    shadow_model_version TEXT NOT NULL,
    shadow_model_hash TEXT NOT NULL,
    shadow_team_probability REAL NOT NULL,
    data_timestamp TEXT,
    payload_json TEXT NOT NULL,
    UNIQUE(fixture_id, generated_at_utc, shadow_model_version)
);
CREATE INDEX IF NOT EXISTS shadow_fixture_time_index
ON shadow_prediction_snapshots(fixture_id, generated_at_utc);
"""


def artifact_hash(path=SHADOW_ARTIFACT):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ensure_shadow_schema(connection):
    connection.executescript(SHADOW_SCHEMA)


def _states(connection):
    states=defaultdict(lambda:{"game":[],"point":[],"straight":[],"five":[],"residual":[]})
    historical=connection.execute("""SELECT i.home_player_id,i.away_player_id,i.winner_side,
      i.game_scores_winner_first,r.home_rating,r.away_rating,m.match_date
      FROM individual_matches i JOIN matches m USING(source_match_id)
      LEFT JOIN individual_match_ratings r USING(individual_match_id)
      ORDER BY m.match_date,m.source_match_id,i.position""").fetchall()
    live=[];live_ratings=defaultdict(list)
    try:
        for rating in connection.execute("SELECT player_id,rating_date,rating FROM live_player_ratings ORDER BY player_id,rating_date"):
            live_ratings[rating["player_id"]].append((rating["rating_date"],float(rating["rating"])))
        live=connection.execute("""SELECT i.home_player_id,i.away_player_id,i.winner_side,
          i.game_scores_winner_first,NULL home_rating,NULL away_rating,m.match_date
          FROM live_individual_matches i JOIN live_matches m USING(source_match_id)
          WHERE m.status='completed' ORDER BY m.match_date,m.source_match_id,i.position""").fetchall()
    except Exception:
        pass
    for row,is_live in [*((row,False) for row in historical),*((row,True) for row in live)]:
        summary=score_summary(row["game_scores_winner_first"]);home_won=row["winner_side"]=="H"
        hr,ar=row["home_rating"],row["away_rating"]
        if is_live:
            def prior(player_id):
                history=live_ratings[player_id];index=bisect_left(history,(row["match_date"],float("-inf")))-1
                return None if index<0 else history[index][1]
            hr,ar=prior(row["home_player_id"]),prior(row["away_player_id"])
        expected=None if hr is None or ar is None else 1/(1+10**(ar-hr))
        for player,won,expect in [(row["home_player_id"],home_won,expected),(row["away_player_id"],not home_won,None if expected is None else 1-expected)]:
            state=states[player]
            if expect is not None: state["residual"].append(float(won)-expect)
            if summary:
                sign=1 if won else -1
                state["game"].append(sign*summary["game_diff"]);state["point"].append(sign*summary["point_diff_per_game"])
                state["straight"].append(int(summary["straight"] and won));state["five"].append(summary["five_game"])
    return states


def _side(state):
    mean=lambda values:float(np.mean(values)) if values else 0.0
    smooth=lambda values:(sum(values)+1)/(len(values)+2)
    return {"game_diff_5":mean(state["game"][-5:]),"straight_rate_10":smooth(state["straight"][-10:]),
      "five_game_rate_10":smooth(state["five"][-10:]),"point_diff_per_game_5":mean(state["point"][-5:]),
      "rating_residual_medium":exponentially_weighted_mean(state["residual"],.70)}


def shadow_context(connection, artifact_path=SHADOW_ARTIFACT):
    return joblib.load(artifact_path), _states(connection)


def score_shadow_projection(connection, production_projection, artifact_path=SHADOW_ARTIFACT,
                            artifact=None, states=None):
    """Score the exact production lineup without changing production output."""
    if artifact is None or states is None:artifact,states=shadow_context(connection,artifact_path)
    models=artifact["models"];rows=[];probabilities=[]
    close_columns=models["columns"]
    for pairing in production_projection["pairings"].to_dict("records"):
        if pairing["team_one_is_forfeit"] or pairing["team_two_is_forfeit"]:
            probability=.5 if pairing["team_one_is_forfeit"] and pairing["team_two_is_forfeit"] else float(pairing["team_two_is_forfeit"])
            branch="forced_forfeit"
        else:
            one,two=int(pairing["team_one_player_id"]),int(pairing["team_two_player_id"]);a,b=sorted((one,two));one_is_a=one==a
            af,bf=_side(states[a]),_side(states[b]);ar=pairing["team_one_rating"] if one_is_a else pairing["team_two_rating"];br=pairing["team_two_rating"] if one_is_a else pairing["team_one_rating"]
            features={"official_rating_diff":ar-br,"position":pairing["position"]}
            for name in ["game_diff_5","straight_rate_10","five_game_rate_10","point_diff_per_game_5","rating_residual_medium"]:features[f"{name}_diff"]=af[name]-bf[name]
            close=abs(features["official_rating_diff"])<SHADOW_THRESHOLD;columns=close_columns if close else POINT_FEATURES;model=models["close"] if close else models["normal"]
            probability_a=float(model.predict_proba(pd.DataFrame([features])[columns])[0,1]);probability=probability_a if one_is_a else 1-probability_a;branch="close" if close else "normal"
        probabilities.append(probability);rows.append({"position":pairing["position"],"team_one_player_id":pairing["team_one_player_id"],"team_two_player_id":pairing["team_two_player_id"],"team_one_rating":pairing.get("team_one_rating"),"team_two_rating":pairing.get("team_two_rating"),"rating_gap":None if pairing.get("team_one_rating") is None or pairing.get("team_two_rating") is None else abs(float(pairing["team_one_rating"])-float(pairing["team_two_rating"])),"production_probability":float(pairing["team_one_probability"]),"shadow_probability":float(probability),"shadow_branch":branch,"team_one_rating_date":pairing.get("team_one_rating_date"),"team_two_rating_date":pairing.get("team_two_rating_date")})
    distribution=lineup_score_distribution(probabilities)
    return {"version":SHADOW_VERSION,"hash":artifact_hash(artifact_path),"team_one_probability":probability_at_least_five(probabilities),"team_one_expected_wins":float(sum(probabilities)),"team_one_score_distribution":[float(value) for value in distribution],"pairings":rows}


def save_shadow_snapshot(connection, fixture, production_projection, shadow_projection,
                         production_version, data_timestamp, generated_at_utc=None):
    ensure_shadow_schema(connection);generated=generated_at_utc or datetime.now(timezone.utc).isoformat()
    payload={"production":{"team_one_probability":float(production_projection["team_one_probability"]),"team_one_expected_wins":float(production_projection["team_one_expected_wins"]),"pairings":[{"position":int(row.position),"team_one_player_id":None if pd.isna(row.team_one_player_id) else int(row.team_one_player_id),"team_two_player_id":None if pd.isna(row.team_two_player_id) else int(row.team_two_player_id),"probability":float(row.team_one_probability),"team_one_rating_date":row.team_one_rating_date,"team_two_rating_date":row.team_two_rating_date} for row in production_projection["pairings"].itertuples()]},"shadow":shadow_projection}
    connection.execute("""INSERT OR IGNORE INTO shadow_prediction_snapshots
      (fixture_id,generated_at_utc,scheduled_match_date,scheduled_match_time,gender,
       team_one_id,team_one_name,team_two_id,team_two_name,prediction_mode,lineup_confidence,
       production_model_version,production_team_probability,shadow_model_version,
       shadow_model_hash,shadow_team_probability,data_timestamp,payload_json)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(fixture["source_match_id"],generated,fixture["match_date"],fixture["match_time"],fixture["gender"],fixture["away_team_id"],fixture["away_team"],fixture["home_team_id"],fixture["home_team"],"projected" if production_projection["mode"].startswith("Current-season") else "preseason",float(production_projection["lineup_confidence"]),production_version,float(production_projection["team_one_probability"]),SHADOW_VERSION,shadow_projection["hash"],float(shadow_projection["team_one_probability"]),data_timestamp,json.dumps(payload,sort_keys=True)))
    return connection.execute("SELECT changes()").fetchone()[0]


def latest_pre_match_snapshots(connection):
    """Latest snapshot strictly before scheduled local date/time; never post-result."""
    ensure_shadow_schema(connection)
    rows=connection.execute("SELECT * FROM shadow_prediction_snapshots ORDER BY fixture_id,generated_at_utc,shadow_snapshot_id").fetchall()
    selected={}
    for row in rows:
        local_date=datetime.strptime(row["scheduled_match_date"],"%Y-%m-%d").date()
        try: local_time=datetime.strptime((row["scheduled_match_time"] or "12:00am").strip().lower(),"%I:%M%p").time()
        except ValueError: local_time=time.min
        cutoff=datetime.combine(local_date,local_time,tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)
        generated=datetime.fromisoformat(row["generated_at_utc"].replace("Z","+00:00"))
        if generated < cutoff:selected[row["fixture_id"]]=row
    return [selected[key] for key in sorted(selected)]


def prospective_evaluation(connection):
    snapshots=latest_pre_match_snapshots(connection);team_rows=[];individual=[]
    for snapshot in snapshots:
        match=connection.execute("SELECT * FROM live_matches WHERE source_match_id=? AND status='completed'",(snapshot["fixture_id"],)).fetchone()
        if not match:continue
        payload=json.loads(snapshot["payload_json"]);actual=int(match["away_score"]>match["home_score"])
        team_rows.append({"fixture_id":snapshot["fixture_id"],"gender":snapshot["gender"],"mode":snapshot["prediction_mode"],"lineup_confidence":snapshot["lineup_confidence"],"actual":actual,"production":snapshot["production_team_probability"],"shadow":snapshot["shadow_team_probability"]})
        verified=connection.execute("SELECT * FROM live_individual_matches WHERE source_match_id=? ORDER BY position",(snapshot["fixture_id"],)).fetchall()
        if len(verified)==9:
            expected={row["position"]:row for row in payload["shadow"]["pairings"]}
            for result in verified:
                pair=expected[result["position"]]
                if pair["team_one_player_id"]==result["away_player_id"] and pair["team_two_player_id"]==result["home_player_id"]:
                    individual.append({"fixture_id":snapshot["fixture_id"],"gender":snapshot["gender"],"position":result["position"],"actual":int(result["winner_side"]=="V"),"production":pair["production_probability"],"shadow":pair["shadow_probability"],"branch":pair["shadow_branch"],"rating_gap":pair.get("rating_gap")})
    return {"team_rows":team_rows,"individual_rows":individual}

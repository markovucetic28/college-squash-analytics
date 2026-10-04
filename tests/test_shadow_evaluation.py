import sqlite3
import pandas as pd
import pytest

from college_squash.shadow_evaluation import (
    SHADOW_VERSION, ensure_shadow_schema, latest_pre_match_snapshots,
    save_shadow_snapshot, score_shadow_projection,
)


def memory_connection():
    connection=sqlite3.connect(":memory:");connection.row_factory=sqlite3.Row;return connection


def fixture():
    return {"source_match_id":1,"match_date":"2026-12-05","match_time":"10:00am","gender":"men","away_team_id":11,"away_team":"Away","home_team_id":22,"home_team":"Home"}


def projection():
    pairings=pd.DataFrame([{"position":position,"team_one_player_id":position,"team_two_player_id":position+20,"team_one_probability":.55,"team_one_rating_date":"2026-10-01","team_two_rating_date":"2026-10-01"} for position in range(1,10)])
    return {"mode":"Preseason projection","team_one_probability":.62,"team_one_expected_wins":4.95,"lineup_confidence":.8,"pairings":pairings}


def shadow():
    return {"version":SHADOW_VERSION,"hash":"abc","team_one_probability":.64,"team_one_expected_wins":5.1,"team_one_score_distribution":[0]*10,"pairings":[]}


def test_shadow_snapshots_are_append_only_idempotent_and_versioned():
    connection=memory_connection();ensure_shadow_schema(connection)
    assert save_shadow_snapshot(connection,fixture(),projection(),shadow(),"production-v1","refresh-1","2026-11-01T12:00:00+00:00")==1
    assert save_shadow_snapshot(connection,fixture(),projection(),shadow(),"production-v1","refresh-1","2026-11-01T12:00:00+00:00")==0
    assert save_shadow_snapshot(connection,fixture(),projection(),shadow(),"production-v1","refresh-2","2026-11-02T12:00:00+00:00")==1
    rows=connection.execute("SELECT * FROM shadow_prediction_snapshots").fetchall()
    assert len(rows)==2 and all(row["shadow_model_version"]==SHADOW_VERSION for row in rows)
    assert all(row["production_model_version"]!="" for row in rows)


def test_latest_snapshot_is_strictly_pre_match_and_rejects_post_result_data():
    connection=memory_connection();ensure_shadow_schema(connection)
    for timestamp in ["2026-12-01T12:00:00+00:00","2026-12-05T14:00:00+00:00","2026-12-05T16:00:00+00:00"]:
        save_shadow_snapshot(connection,fixture(),projection(),shadow(),"production-v1","refresh",timestamp)
    selected=latest_pre_match_snapshots(connection)
    assert len(selected)==1
    # 10am Eastern is 15:00 UTC; the 16:00 post-match snapshot is excluded.
    assert selected[0]["generated_at_utc"]=="2026-12-05T14:00:00+00:00"


def test_shadow_uses_same_nine_lineup_slots_and_exact_aggregation():
    from college_squash.preseason import predict_preseason_matchup
    from college_squash.database import connect_database
    import joblib
    project_database=connect_database("data/college_squash.db")
    artifact=joblib.load("data/preseason_player_model.joblib")
    production=predict_preseason_matchup(project_database,artifact,"Fordham University","St. Lawrence University","men")
    result=score_shadow_projection(project_database,production)
    assert len(result["pairings"])==len(production["pairings"])==9
    assert [row["team_one_player_id"] for row in result["pairings"]]==production["pairings"]["team_one_player_id"].tolist()
    assert sum(result["team_one_score_distribution"])==pytest.approx(1)
    project_database.close()


def test_shadow_preserves_short_roster_forfeit_rule():
    from college_squash.preseason import predict_preseason_matchup
    from college_squash.database import connect_database
    import joblib
    connection=connect_database("data/college_squash.db");artifact=joblib.load("data/preseason_player_model.joblib")
    production=predict_preseason_matchup(connection,artifact,"Dickinson College","Harvard University","women")
    result=score_shadow_projection(connection,production)
    assert len(result["pairings"])==9
    assert result["pairings"][-1]["shadow_branch"]=="forced_forfeit"
    assert result["pairings"][-1]["shadow_probability"]==0
    connection.close()

import pandas as pd
import pytest

from scripts.audit_matchup_probabilities import (
    GAP_EDGES, GAP_LABELS, bucket_report, team_calibration,
)


def test_rating_gap_buckets_are_mutually_exclusive_at_boundaries():
    frame=pd.DataFrame({
        "official_rating_diff":[.0,.049,.05,.099,.10,.149,.15,.199,.20,.299,.30,.499,.50],
        "production_probability":[.5]*13,"player_a_win":[1]*13,
    })
    rows=bucket_report(frame,"production_probability",GAP_EDGES,GAP_LABELS)
    assert sum(row["matches"] for row in rows)==len(frame)
    assert [row["matches"] for row in rows]==[2,2,2,2,2,2,1]


def test_team_calibration_uses_predicted_favorite_orientation():
    frame=pd.DataFrame({"probability":[.55,.35,.92],"actual":[1,0,1]})
    rows=team_calibration(frame,"probability")
    assert sum(row["matches"] for row in rows)==3
    assert all(row["actual_win_rate"]==pytest.approx(1) for row in rows)

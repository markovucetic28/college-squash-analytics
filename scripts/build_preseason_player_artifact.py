from datetime import datetime, timezone
from pathlib import Path
import sys

import joblib


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from college_squash.database import connect_database
from college_squash.player_modeling import (
    OFFICIAL_RATING_FEATURES, _model, build_player_feature_dataset,
)


def main():
    with connect_database(PROJECT_ROOT / "data/college_squash.db") as connection:
        features = build_player_feature_dataset(connection)
    training = features[features["official_rating_diff"].notna()].copy()
    model = _model()
    model.fit(training[OFFICIAL_RATING_FEATURES], training["player_a_win"])
    artifact = {
        "model": model,
        "features": OFFICIAL_RATING_FEATURES,
        "trained_through": "2025-26",
        "training_individual_matches": len(training),
        "methodology": "Unchanged official-rating logistic regression",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    path = PROJECT_ROOT / "data/preseason_player_model.joblib"
    joblib.dump(artifact, path)
    print(f"Saved {path} from {len(training):,} rated individual matches")


if __name__ == "__main__":
    main()

# Model Research

This document summarizes the main modeling experiments behind College Squash Analytics.

The production model remains fixed. Research models are evaluated separately and are not used by the live API unless explicitly promoted.

All historical experiments use only information that would have been available before each match, including strictly prior rating timestamps and walk-forward evaluation.

---

## Current production baseline

The production individual model uses pre-match player ratings and lineup context.

On held-out historical data it achieved approximately:

- **85% accuracy**
- **0.340 log loss**
- **0.105 Brier score**

For verified team lineups, exact aggregation of individual probabilities reached about **92.6% historical accuracy**.

---

## Main research directions

### Richer player features

I tested whether additional recent-performance features could improve player-level predictions beyond the production baseline.

Features tested included:

- Recent game differential
- Point margin
- Straight-game frequency
- Five-game frequency
- Lineup position
- Historical performance residuals

The best richer model slightly improved probability quality over the production baseline, especially for closer matchups.

---

### Close-match model

A two-stage model performed best in research testing:

- **Rating gap >= 0.30:** point-dominance model
- **Rating gap < 0.30:** point dominance + medium-decay performance residual

This setup improved Brier score and log loss on the untouched 2025–26 season.

The main goal was to improve close-match probability quality without making large changes to already well-separated matchups.

---

### Robustness and calibration

Additional testing included:

- Bootstrap confidence intervals
- Probability-shift analysis
- Sparse-history cases
- Gender-specific models
- Uncertainty weighting
- Calibration by rating gap
- Team-level probability calibration
- Historical-depth comparisons
- Recency-decay experiments

The unified model performed more consistently than separate gender-specific models, so the project kept one shared model.

Longer training histories and additional decay schemes did not produce a meaningful enough improvement to justify replacing the current training setup.

Overall, the results did not support more aggressive retrospective tuning.

---

## Best research candidate

The best research-only candidate is the simplified two-stage model.

External 2025–26 performance:

- **Individual accuracy:** about 85.5%
- **Individual Brier:** about 0.102
- **Verified-lineup team accuracy:** about 90.6%
- **Verified-lineup Brier:** about 0.071

The candidate showed small improvements over production on several evaluation metrics, but the gains were not large or consistent enough to justify replacing the production model.

---

## Team probability validation

For team matches, the model combines the nine individual matchup probabilities using an exact Poisson-binomial calculation.

Historical testing showed strong calibration at the team level.

For example, among historical team predictions above 95%:

- Average predicted favorite probability: about **99.3%**
- Actual favorite win rate: about **99.3%**

This supported keeping the existing exact five-of-nine aggregation rather than artificially reducing extreme probabilities.

---

## Historical-depth study

I also tested whether using more seasons of historical data improved model quality.

The available verified training seasons were compared using progressively larger training windows.

The main findings were:

- Individual prediction quality had largely plateaued.
- Verified-lineup improvements from more seasons were small.
- Projected-lineup predictions showed a modest benefit from using the full available training history.
- Additional season-decay weighting did not meaningfully improve results.
- Older rating scales showed some drift, making incomplete older data less attractive to include.

Based on these results, the current verified training history was retained rather than adding lower-quality older data.

---

## Prospective evaluation

The current research model is evaluated in shadow mode on future 2026–27 matches.

Production and candidate predictions are stored separately before match results are known.

The system records:

- Prediction timestamp
- Model version
- Model artifact hash
- Player ratings and rating dates
- Projected lineup
- Individual matchup probabilities
- Team probability
- Expected wins

Only predictions created strictly before match time are eligible for evaluation.

This makes it possible to compare the production and research models on genuinely unseen data without changing the public model.

---

## Research code

Reusable research modules:

- `src/college_squash/player_model_research.py`
- `src/college_squash/close_match_research.py`
- `src/college_squash/model_robustness.py`
- `src/college_squash/model_stabilization.py`
- `src/college_squash/model_uncertainty.py`
- `src/college_squash/gender_model_research.py`

Evaluation scripts:

- `scripts/evaluate_richer_player_model.py`
- `scripts/evaluate_close_match_model.py`
- `scripts/stabilize_close_match_model.py`
- `scripts/evaluate_uncertainty_model.py`
- `scripts/evaluate_gender_models.py`
- `scripts/audit_close_match_promotion.py`
- `scripts/evaluate_historical_depth.py`
- `scripts/evaluate_shadow_predictions.py`

Generated outputs and research artifacts are stored under ignored `data/processed/` directories and are not used by the production API.

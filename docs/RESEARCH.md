# Model research inventory

Prediction-model research is frozen. None of the modules or scripts listed here
is imported by the production API, and generated artifacts remain under ignored
`data/processed/` directories.

## Reusable research infrastructure

- `src/college_squash/player_model_research.py`: leakage-safe individual-match feature construction.
- `src/college_squash/close_match_research.py`: close-match, calibration, upset, and probability-shift diagnostics.
- `src/college_squash/model_robustness.py`: history buckets and clustered bootstrap helpers.
- `src/college_squash/model_stabilization.py`: research-only shrinkage, gates, clipping, and fallback helpers.
- `src/college_squash/model_uncertainty.py`: weighted variance, ESS, uncertainty, and blending helpers.
- `src/college_squash/gender_model_research.py`: gender-isolation and interaction helpers.

These modules stay at their existing paths for now. Moving all imports into a new
package would create broad churn without changing behavior; a package migration
should happen only when another research cycle actually needs it.

## Candidate-model research scripts

- `scripts/evaluate_richer_player_model.py`: broader player-feature comparison.
- `scripts/evaluate_close_match_model.py`: point-dominance and close-match experiments.
- `scripts/stabilize_close_match_model.py`: simplified candidate and safeguard diagnostics.
- `scripts/evaluate_uncertainty_model.py`: ESS, variance, empirical-Bayes, and soft-blending experiments.
- `scripts/evaluate_gender_models.py`: unified versus gender-aware and separate models.

## Robustness audit

- `scripts/audit_close_match_promotion.py`: promotion-readiness and subgroup checks.

## Tests

- `tests/test_player_model_research.py`
- `tests/test_close_match_research.py`
- `tests/test_model_robustness.py`
- `tests/test_model_stabilization.py`
- `tests/test_model_uncertainty.py`
- `tests/test_gender_model_research.py`

## Generated output

Research reports, prediction exports, coefficient tables, bootstrap results, and
candidate artifacts live under ignored `data/processed/*research*/` or similarly
named model-research directories. Candidate artifacts are not production models.

No current file was classified as safely obsolete: each retained script represents
a distinct completed milestone and is required to reproduce its reported result.

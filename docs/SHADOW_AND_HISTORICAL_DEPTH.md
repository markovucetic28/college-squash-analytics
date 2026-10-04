# Shadow evaluation and historical-depth study

These are separate local-only workstreams. Nothing in this milestone changes the
model loaded by the public API or exposes research probabilities in the UI.

## Part A: prospective shadow evaluation

Candidate: `simplified-two-stage-v1`

- artifact: `data/processed/model_stabilization/stabilized_candidate.joblib`
- SHA-256: `7b576da8fc85b58416a807ba8de392b5ae562951f733555067e7890f25199d9e`
- trained through: 2024–25
- routing: absolute rating gap below 0.30 uses the fixed close model; otherwise
  the fixed point-dominance model
- unified for men and women; no uncertainty blend and no explicit interaction

The updater scores the exact same ordered lineup through production and shadow.
It stores one combined append-only record with model versions, probabilities,
individual pairings, player IDs, rating dates, branches, confidence, schedule,
and data timestamp. A refresh creates a new timestamped snapshot rather than
updating an earlier row. Repeating the identical timestamp/version is idempotent.

The authoritative evaluation record is the latest snapshot generated strictly
before scheduled match time. Post-match snapshots are excluded. Completed live
matches attach outcomes to this immutable snapshot; verified individual results
are evaluated only when the player IDs and positions match the projected pair.

The evaluator reports production and shadow accuracy, log loss, Brier and ECE at
individual/team level, below rating gaps 0.30/0.20/0.10, by gender, mode and
lineup-confidence band. Checkpoints are 100/250/500/1,000 rated individuals and
25/50/100/250 teams. Current prospective sample size is zero because no saved
fixture has completed since shadow mode was introduced.

## Part B: historical depth

Verified seasons available locally are 2019–20 and 2021–22 through 2025–26.
There was no 2020–21 CSA season. The official CSA archive confirms rankings for
2018–19 and earlier, but rankings and previews do not establish complete match
results, nine-position scorecards, stable player IDs and leakage-safe historical
ratings. No older data was downloaded or inferred.

Therefore 8- and 10-season experiments are unavailable. The executed sensitivity
study compares the last three, four and all five pre-2025–26 training seasons,
with equal weights and season-decay factors 0.90, 0.80 and 0.65. Features and the
0.30 routing threshold remain fixed.

### Data quality

Both-player rating coverage improves from 83.0% in 2019–20 and 85.1% in 2021–22
to 96.9–98.1% from 2022–23 onward. Complete nine-position lineup coverage ranges
from 72.5% to 80.2%. Verified point scores are effectively complete.

Mean rating rises from 4.65 in 2019–20 to 5.50 in 2025–26, while median rises
from 4.77 to 5.61. Rating-gap favorite win rates are nevertheless broadly stable;
the oldest period is somewhat less decisive for gaps over 0.30. This is evidence
for caution when adding much older equal-weight data.

### External 2025–26 results

| Training window | Individual Brier | Log loss | Verified-team Brier | Projected-team Brier |
|---|---:|---:|---:|---:|
| 3 seasons, equal | 0.10193 | 0.32027 | 0.07181 | 0.09154 |
| 4 seasons, equal | 0.10203 | 0.32106 | 0.07149 | 0.09053 |
| 5 seasons, equal | 0.10198 | 0.32090 | 0.07118 | 0.09020 |
| 5 seasons, mild decay | 0.10196 | 0.32075 | 0.07126 | 0.09036 |
| 5 seasons, stronger decay | 0.10196 | 0.32054 | 0.07150 | 0.09081 |

Individual performance is effectively flat. Five seasons improve verified and
projected team Brier modestly. Men and women remain stable under one unified
model; women do not show evidence that a separate model is required.

The 2,000-resample five-minus-three Brier intervals are:

- individual: +0.000056, 95% interval [-0.000406, +0.000508]
- verified team: -0.000619, interval [-0.001631, +0.000462]
- projected team: -0.001334, interval [-0.002490, -0.000260]

For 408 unlabeled current fixtures, three- versus five-season team probabilities
differ by 0.47 points on average, 0.06 median and 1.51 at the 90th percentile.
One fixture shifts over five points and none shifts over ten. More verified
history barely changes the current distribution.

### Decision

**A — the current five-season training history is sufficient.** This does not
claim that a reliable 8/10-season dataset could never help. It means the verified
learning curve has plateaued, decay choices are nearly indistinguishable, and
there is currently no lawful, validated extended scorecard/rating dataset with
which to test a longer window.

Machine-readable output is in `data/processed/historical_depth/evaluation.json`.

# Matchup probability audit

Local-only audit performed against the frozen production model and the existing
research-only simplified two-stage artifact. No model or database was changed.

## Fordham vs. St. Lawrence

The December 5, 2026 projected lineup reproduces Fordham at 18.78395% and St.
Lawrence at 81.21605%. Expected individual wins are 3.40860 and 5.59140.

Nathan Cukierman (6.195701) vs. Mina Yousef (6.322927) is position 1. The rating
difference is -0.127226 from Fordham's perspective. The production logit is
-0.854197: standardized rating contributes -1.416273, position contributes only
+0.007074, and the intercept is +0.555003. Probabilities for Cukierman are:

- rating-only diagnostic: 29.8312%
- production: 29.8553%
- point-dominance candidate: 32.7731%
- simplified two-stage candidate: 38.2850%

Cukierman's recent rating residual is +0.3075 versus Yousef's -0.1607. Recent
point margin is +4.48 versus -0.62 points per game. Those research features move
the simplified candidate toward Cukierman; production intentionally does not use
them.

The exact Fordham win-count distribution from zero through nine wins is:

`0.005939, 0.051576, 0.174350, 0.299007, 0.281288, 0.145239, 0.038327, 0.004198, 0.000076, 0.00000036`

The largest one-position sensitivity changes when replacing a probability with
50% are positions 3 (+13.82 percentage points for Fordham), 2 (+13.71), 9
(+7.99), 1 (+5.22), and 4 (-4.57). The simplified pairings aggregate to 23.66%
for Fordham, 4.88 points above production.

## Individual calibration

Across 17,727 held-out individual matches:

| Rating gap | Matches | Observed favorite wins | Production average | Simplified average |
|---|---:|---:|---:|---:|
| 0.00–0.05 | 1,594 | 53.26% | 54.06% | 53.96% |
| 0.05–0.10 | 1,523 | 61.79% | 61.81% | 62.24% |
| 0.10–0.15 | 1,409 | 70.76% | 68.50% | 69.61% |
| 0.15–0.20 | 1,467 | 77.51% | 74.55% | 75.79% |
| 0.20–0.30 | 2,850 | 84.21% | 82.35% | 83.67% |
| 0.30–0.50 | 3,785 | 94.56% | 91.64% | 91.67% |
| 0.50+ | 6,099 | 98.57% | 98.61% | 98.62% |

The fine 0.025-wide curve does not show excessive production steepness below a
0.30 gap. Production is slightly conservative through most of 0.10–0.30.

For gaps below 0.30, positions 1–3, 4–6, and 7–9 have observed favorite win
rates of 71.18%, 71.46%, and 71.95%, with production averages of 70.16%, 70.01%,
and 70.49%. Position does not create the Cukierman–Yousef confidence.

## Team calibration and dependence

There are 1,674 complete held-out team matches. Production accuracy/log loss/
Brier are 91.88% / 0.2021 / 0.06283. Simplified results are 91.82% / 0.1999 /
0.06211. In the 95%+ bucket, production averages 99.31% and favorites win
99.31%, which is unusually direct evidence that the extreme team probabilities
are not generally overstated in this sample.

The mean residual correlation across lineup positions is 0.0064 (median 0.0037)
over 2,197 matches. This simple diagnostic finds no material shared match-day
dependence, though lineup errors and selection effects remain possible.

## Current schedule

Among 408 projectable fixtures, production versus simplified absolute team-
probability differences have mean 0.83 points, median 0.02, and 90th percentile
2.76. Eighteen differ by more than five points, two by more than ten, and none by
more than fifteen.

Production favorite probabilities are high because the schedule contains many
large rating mismatches: median 99.88%, mean 94.22%; 89.0% are at least 80%,
79.7% at least 90%, and 71.3% at least 95%. Historical calibration supports
these extremes better than intuition alone would suggest.

## Conclusion

Classification: **A — production behavior is supported; intuition was
misleading for this example.** The exact aggregation is correct, close-rating
production probabilities are broadly calibrated and sometimes conservative,
position has negligible influence in the audited pairing, and residual
correlation does not indicate a material independence failure. The simplified
candidate remains research-only.

Machine-readable results are in
`data/processed/matchup_probability_audit/audit.json`; supporting CSVs contain
the continuous gap curve, rating-gap buckets, and current-fixture comparison.

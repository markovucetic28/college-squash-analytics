# College Squash Analytics

Python project for collecting, validating, storing, and exploring varsity college squash team results. The current database covers six completed CSA seasons from 2019–20 through 2025–26, with the missing 2020–21 season documented rather than inferred.

The production prediction artifacts are currently frozen. Later point-dominance,
close-match, uncertainty, and gender-model experiments remain local research
candidates and are not loaded by the API. See `docs/RESEARCH.md` for the inventory.

## Coverage

| Season | Men's varsity teams | Women's varsity teams | Verified matches |
|---|---:|---:|---:|
| 2019–20 | 35 | 32 | 645 |
| 2021–22 | 34 | 32 | 583 |
| 2022–23 | 34 | 32 | 551 |
| 2023–24 | 34 | 32 | 538 |
| 2024–25 | 34 | 31 | 599 |
| 2025–26 | 34 | 31 | 621 |
| **Total** | **395 team-seasons** |  | **3,537** |

The source is the public College Squash Association organization in Club Locker. Each season uses the official men's and women's master division schedule and standings endpoints. Raw JSON and retrieval metadata are stored in `data/raw/`; processed CSVs and SQLite are reproducible outputs.

For 2019–20 through 2022–23, master divisions contain varsity and club teams together. Inclusion uses Club Locker's explicit `CollegeTeamType == "Varsity"` value, not a name guess. The 2023–24 through 2025–26 seasons have dedicated varsity divisions. The official 2026–27 schedule is also collected, but scheduled fixtures are kept outside the completed-match dataset.

## Known coverage gaps

- There is no 2020–21 season in this dataset. The pandemic prevented a normal CSA varsity season, so no results are fabricated.
- Some earlier postseason cup matches are stored by Club Locker in separate championship divisions rather than the season's master division. The current historical totals therefore describe verified matches captured in the master feeds, not guaranteed complete school season records. For example, the 2019–20 men's standings show Harvard at 17–0 while 14 Harvard matches are present in the master schedule feed.
- A small number of unconfirmed, tied/incomplete, malformed, or club-versus-club rows are logged as exclusions.
- Outside-division opponents are retained when they played a varsity team, but their records may be incomplete. This affects strength of schedule.
- Prediction quality is limited by the master-feed coverage gaps, especially separately stored postseason matches in older seasons.

## Setup and reproducible build

Python 3.11 or newer is recommended.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Download official public snapshots with a descriptive user agent and a one-second delay between requests:

```bash
PYTHONPATH=src python -m college_squash.clublocker
```

Build CSV outputs and SQLite:

```bash
python scripts/build_dataset.py
python scripts/build_database.py
```

Run analytics or the app:

```bash
python scripts/show_team.py "Harvard University" --gender men --season 2024-25
streamlit run app.py
pytest
```

## FastAPI and Next.js web application

The polished web interface is an incremental replacement for Streamlit. Streamlit
remains available as a reference while the routed application reaches full feature
parity. Python remains the source of truth for every database query, analytic, lineup
projection, and probability; the TypeScript frontend only presents API responses.

Architecture:

```text
CSA / Club Locker → Python ingestion → SQLite → Python analytics and models
                                                   ↓
                                                FastAPI
                                                   ↓
                                       Next.js / React / TypeScript
```

Start the API from the project root:

```bash
source .venv/bin/activate
PYTHONPATH=src uvicorn college_squash.api:app --reload --port 8000
```

In another terminal, start the frontend:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. Set `NEXT_PUBLIC_API_BASE_URL` from
the root `.env.example` only when the API is served somewhere other than
`http://127.0.0.1:8000`.

The frontend provides durable routes for:

- `/schedule`: all 426 current fixtures with division, team, and date filters
- `/match/[match_id]`: prediction mode, expected score, positions 1–9, player
  ratings, individual probabilities, confidence, team context, and prior meetings
- `/teams` and `/team/[team_id]`: official rosters, ratings, projected order,
  schedule, verified results, and multi-season history
- `/player/[player_id]`: current or historical identity, verified record, matches,
  roster history, and rating history
- `/rankings`: men's and women's project rankings for every covered season
- `/compare`: player-first projected lineup comparison plus team context
- `/methodology`: sources, leakage rules, prediction modes, external validation,
  and limitations

FastAPI exposes `/api/schedule`, `/api/matches/{match_id}`, `/api/teams`,
`/api/teams/{team_id}`, `/api/players/search`, `/api/players/{player_id}`,
`/api/rankings`, `/api/compare`, `/api/search`, and
`/api/methodology/summary`. Interactive API documentation is available at
`http://127.0.0.1:8000/docs` while the backend is running.

### Search behavior

Player search covers all 837 official 2026–27 roster identities plus historical
players. It normalizes case, punctuation, apostrophes, hyphens, whitespace,
accents, and `Last, First` versus `First Last` order. Token prefixes allow a query
such as `char raven` to find `Raven, Charlie`. Current-only newcomers remain
searchable even with no verified college matches. Team, division, and season are
shown for ambiguous player names, and an empty query returns no result.

## Validation rules

A match is included only when it is confirmed, has both teams and identifiers, contains two integer scores with a winner, and includes at least one officially classified varsity team. Exact Club Locker scorecard IDs must be unique. A natural key of date, division, teams, and match time catches duplicates while preserving legitimate same-day doubleheaders. Excluded rows keep their source page and reason.

Team-name changes are handled with a small explicit alias list. Source names are preserved separately. Stable `programs` records link season-specific team IDs, so names such as `Pennsylvania, University of` and `University of Pennsylvania`, or `Bowdoin College Men` and `Bowdoin College`, resolve to one program without assuming arbitrary fuzzy matches.

## SQLite schema

- `sources`: one provenance record per season/division feed
- `divisions`: gender, season, official division ID, and source
- `programs`: stable canonical program identity by name and gender
- `teams`: season-specific Club Locker team ID, original name, canonical program, and varsity flag
- `matches`: scorecard ID, division, season, date/time, participants, scores, and venue
- `scheduled_matches`: 2026–27 fixtures and provenance, with no score columns and no path into completed-result analytics
- `current_roster_players`: official 2026–27 roster membership, roster rating, collection date, and source URL

Foreign keys, score checks, program/division uniqueness, source-ID uniqueness, natural match uniqueness, and indexes are applied during every rebuild.

## Analytics definitions

- **Record and win percentage:** confirmed wins divided by confirmed matches in the selected season or program-history scope.
- **Recent form:** the five most recent verified results in the selected scope.
- **Player recent-form indicator:** descriptive average performance versus the
  frozen official-rating model's pre-match expectation over up to five rated
  matches. At least three matches are required. Scores of +0.10 or higher are
  shown as above expectations, −0.10 or lower as below expectations, and values
  between them as broadly expected. This indicator never changes predictions.
- **Average margin:** mean team score minus opponent score.
- **Strength of schedule:** mean season win percentage of every opponent faced, counting repeat opponents once per match. Program-history SOS is the match-weighted mean of season-specific SOS values.
- **Head-to-head:** confirmed meetings between two stable program identities, optionally filtered to one season.
- **Project ranking:** season win percentage, then season strength of schedule, then average margin, with name as a deterministic final tie-breaker. It is not an official CSA ranking.

## Streamlit product

The app now has five task-focused views:

- **Schedule:** the default experience; all fixtures are filterable and every match opens a detailed preseason matchup
- **Teams:** current roster and ratings, likely order, complete schedule, historical results, and season summaries
- **Rankings:** compact project rank, record, Elo, schedule strength, margin, and form
- **Compare:** projected positions 1–9, individual probabilities, expected score, overall probability, team context, and prior meetings
- **Methodology:** concise provenance, leakage, preseason projection, validation, and limitation notes

A global player autocomplete searches both current and historical roster identities
with team context, then opens a detail view with rating history, positions, and
verified college results.

Ordinary pages query only required SQLite rows. Schedule and ranking queries are cached, and a player page fetches rating history for one player rather than loading the roughly 1.4 million-row ratings table.

### 2026–27 current-season refresh

Refresh the official schedule and standings without player requests:

```bash
python scripts/update_current_season.py --schedules-only
python scripts/build_database.py
```

Run the full incremental refresh after results begin. Existing scorecards are reused, unchanged JSON is not rewritten, changed rating histories preserve the prior snapshot, and the readiness report is written to `data/processed/current_season_readiness.json`.

```bash
python scripts/update_current_season.py
python scripts/build_database.py
```

Roster-only refreshes reuse the saved schedule and do not fetch ratings or scorecards:

```bash
python scripts/update_current_season.py --rosters-only
python scripts/load_current_rosters.py
```

The October 2, 2026 schedule snapshot contains 426 validated fixtures: 234 men’s and 192 women’s. Two feed rows were excluded because neither participant appears in the official varsity standings. The current roster snapshot indexes 837 unique players across 65 teams; every indexed player has a roster rating. There are no confirmed 2026–27 results yet.

### Preseason projections

A preseason lineup is available only from an official 2026–27 roster. The nine
highest current roster ratings form the projected order. Prior 2025–26 varsity
appearances contribute to a separate lineup-confidence score but cannot make a
player eligible, so graduated or transferred players are never carried forward
unless they appear on the current roster. One women’s roster currently has only
eight players; outside-division club opponents also lack varsity rosters.

The individual probability model is the unchanged official-rating logistic
regression using rating difference and position. Its prospective artifact is fit
through 2025–26 from 22,590 rated individual matches. Nine position probabilities
are combined with the exact Poisson-binomial calculation already used by the
validated lineup model. This supports preseason projections for 396 fixtures
(223 men’s and 173 women’s). Each result is labeled **Preseason projection** and
is not presented as a confirmed lineup.

Prediction modes are labeled explicitly: verified lineups use an actual official
lineup; projected lineups use recent official lineup evidence; preseason
projections use the current roster, current ratings, and prior lineup evidence;
team-only estimates are used when a playable player lineup is unavailable.

The status endpoint and site header expose the last successful refresh, schedule
and rating timestamps when available, and a compact prediction-data readiness
message. Internal errors, paths, and stack traces are not shown publicly.

Recreate the small production artifact without changing the model methodology:

```bash
python scripts/build_preseason_player_artifact.py
```

## Matchup model

The model predicts whether alphabetically ordered Team A wins. Alphabetical ordering avoids treating Club Locker's home label as a reliable venue signal for neutral-site matches. Logistic regression uses standardized differences in:

- current-season pre-match win percentage
- prior-season program strength, with older completed seasons decayed by 60% per season
- form over the previous five current-season matches
- current-season average pre-match scoring margin
- current-season strength of schedule as it stood before the match
- Elo rating
- decayed historical head-to-head advantage

Current-season statistics reset each season. Elo carries 75% of its distance from 1500 into the next season, reflecting roster turnover. Historical head-to-head counts decay by 60% at each season boundary. Training observations are weighted by 75% for each season of age. These constants are intentionally simple and documented rather than tuned against the holdouts.

All matches on one calendar date are scored before any results from that date update features or Elo. Evaluation is expanding-window walk-forward validation:

| Held-out season | Training matches | Test matches | Win-% baseline accuracy | Elo accuracy | Logistic accuracy | Logistic log loss | Logistic Brier |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2021–22 | 645 | 583 | 60.5% | 65.0% | 74.3% | 0.542 | 0.180 |
| 2022–23 | 1,228 | 551 | 63.7% | 73.5% | 75.7% | 0.464 | 0.153 |
| 2023–24 | 1,779 | 538 | 63.8% | 70.4% | 79.9% | 0.429 | 0.139 |
| 2024–25 | 2,317 | 599 | 62.6% | 74.0% | 81.8% | 0.408 | 0.131 |

Aggregate held-out results:

| Method | Accuracy | Log loss | Brier score |
|---|---:|---:|---:|
| Higher pre-match win percentage | 62.6% | 0.642 | 0.225 |
| Elo | 70.7% | 0.602 | 0.206 |
| Logistic regression | 77.9% | 0.461 | 0.151 |

Because logistic regression beats both baselines on all three aggregate metrics and in accuracy for every held-out season, the all-history comparison page displays a future matchup estimate. It is explicitly labeled as a project-generated estimate, not an official CSA forecast or certainty.

Build the feature dataset, rerun walk-forward validation, and save the final recency-weighted model with:

```bash
python scripts/build_model.py
```

## Model sanity checks

Run the unchanged model's diagnostic suite with:

```bash
python scripts/validate_model.py
```

This recreates the same out-of-fold predictions without changing features, constants, hyperparameters, or the production artifact.

### Target balance and gender

Alphabetically defined Team A won 45.8%, 43.6%, 43.7%, and 44.1% of held-out matches by season. A majority-class rule would therefore achieve only 54.2%–56.4%, far below the model.

| Group | Matches | Win-% baseline accuracy | Elo accuracy | Model accuracy | Model log loss | Model Brier |
|---|---:|---:|---:|---:|---:|---:|
| Men | 1,222 | 61.3% | 70.3% | 76.8% | 0.474 | 0.156 |
| Women | 1,049 | 64.2% | 71.2% | 79.2% | 0.445 | 0.145 |

The model beats both baselines for both groups. Its held-out accuracy rises across seasons for both groups, reaching 81.5% for men and 82.1% for women in 2024–25.

### Matchup difficulty

Closeness uses absolute pre-match Elo difference: under 50 is very close, 50–99 moderately close, 100–199 a clear favorite, and 200+ a heavy favorite.

| Elo gap | Matches | Win-% baseline accuracy | Elo accuracy | Model accuracy | Model log loss | Model Brier |
|---|---:|---:|---:|---:|---:|---:|
| Very close | 1,084 | 50.5% | 59.0% | 71.3% | 0.561 | 0.189 |
| Moderately close | 672 | 65.0% | 72.8% | 77.1% | 0.490 | 0.159 |
| Clear favorite | 460 | 84.3% | 92.2% | 92.6% | 0.225 | 0.061 |
| Heavy favorite | 55 | 90.9% | 96.4% | 96.4% | 0.098 | 0.027 |

Easy matches help overall accuracy, but they do not explain the whole result: 77% of holdouts have an Elo gap below 100, and the model still reaches 71.3% on the closest group. Very-close accuracy ranges from 66.0% to 75.1% across individual seasons.

### Confidence and calibration

| Predicted favorite confidence | Matches | Mean confidence | Favorite win rate | Gap |
|---|---:|---:|---:|---:|
| 50–60% | 337 | 55.1% | 53.1% | -1.9 points |
| 60–70% | 366 | 64.9% | 65.0% | +0.1 points |
| 70–80% | 419 | 75.0% | 74.7% | -0.3 points |
| 80–90% | 506 | 85.2% | 85.8% | +0.6 points |
| 90–100% | 643 | 94.6% | 94.2% | -0.4 points |

Fixed-width reliability bins give aggregate expected calibration error of 0.012. Seasonal ECE ranges from 0.025 to 0.049. This is encouraging internal calibration evidence, but ECE depends on binning and these are not independent external seasons, so the project does not claim definitive calibration.

### Dominant teams, repeat opponents, and upsets

A dominant team is defined before the match as either program having Elo of at least 1700. Only 87 of 2,271 holdouts meet that definition. Removing them leaves model accuracy at 77.5%, compared with 77.9% overall, so a few dominant programs are not driving the result.

The repeated-matchup check exposes a meaningful weakness:

| Prior meeting available | Matches | Model accuracy | Log loss | Brier |
|---|---:|---:|---:|---:|
| Yes | 1,855 | 80.4% | 0.431 | 0.138 |
| No | 416 | 66.8% | 0.593 | 0.205 |

Prior head-to-head is legitimate pre-match information, but 81.7% of holdouts involve programs that have met previously. Overall performance therefore does not transfer fully to first-time pairings. In 2022–23 and 2024–25, first-time accuracy is only 58.8% and 62.8% respectively.

An Elo upset is a match won by the lower pre-match Elo team. Upsets account for 665 of 2,271 matches, or 29.3%. Elo is necessarily 0% accurate on that conditioned subset. Logistic regression identifies 49.6% of those winners, but its upset-only log loss is 0.885 and Brier score is 0.315, slightly worse than Elo's 0.824 and 0.314. The model therefore changes the selected winner for many upsets but is not reliably assigning better probabilities within this difficult subset.

### Coefficients

Coefficients are for standardized features, so their magnitudes are comparable. Positive values favor alphabetically ordered Team A when its feature value is higher.

| Feature | Mean fold coefficient | Interpretation |
|---|---:|---|
| Average margin difference | +1.075 | Strongest and most consistent positive signal |
| Strength-of-schedule difference | +0.708 | Strong positive signal across every fold |
| Head-to-head difference | +0.699 | Increasingly strong in later folds |
| Elo difference | +0.312 | Positive after enough historical seasons accumulate |
| Recent-form difference | +0.054 | Small incremental contribution |
| Prior-season strength difference | +0.006 | Nearly zero after correlated features are included |
| Current win-percentage difference | -0.061 | Unstable sign across folds, likely due to collinearity |

No single standardized coefficient is overwhelmingly larger than every other useful signal, although average margin is consistently largest. The unstable current-win coefficient and growing head-to-head coefficient warrant caution. Coefficients describe conditional associations in correlated inputs, not isolated causal importance.

## Historical sample checks

The stable program mapping produces these master-feed histories:

| Program | 2019–20 | 2021–22 | 2022–23 | 2023–24 | 2024–25 |
|---|---:|---:|---:|---:|---:|
| Harvard men | 14–0 | 15–1 | 14–0 | 10–3 | 10–7 |
| Penn men | 12–2 | 18–1 | 15–1 | 12–2 | 20–0 |
| Trinity women | 14–3 | 15–2 | 16–0 | 14–0 | 18–1 |

These calculations are checked directly against the saved official schedule rows. The 2024–25 Harvard, Penn, and Trinity records also match the independent school sources used in the original milestone. Earlier differences from standings are explicitly treated as coverage gaps, primarily separately stored postseason matches.

## Player-level lineup research

This milestone uses the public Club Locker scorecard-list and historical team-roster endpoints. Raw responses are saved separately under `data/raw/player_scorecards/` and `data/raw/player_rosters/`; every normalized individual result retains its official scorecard URL. Run the checkpointed collector, validation/export, database rebuild, and evaluation with:

```bash
python scripts/collect_player_data.py
python scripts/export_player_dataset.py
python scripts/build_database.py
python scripts/build_player_model.py
```

Only completed singles positions 1S through 9S count. Position 10 and other reserve/exhibition rows are excluded. A scorecard is loaded only when all nine positions are unique, both official player IDs are present, and its nine winners exactly reproduce the stored team score. Incomplete pages are listed in `data/processed/individual_match_exclusions.csv`; no player or result is inferred.

| Season | Team matches | Complete lineups | Individual matches | Complete coverage |
|---|---:|---:|---:|---:|
| 2019–20 | 645 | 517 | 4,653 | 80.2% |
| 2021–22 | 583 | 459 | 4,131 | 78.7% |
| 2022–23 | 551 | 413 | 3,717 | 74.9% |
| 2023–24 | 538 | 421 | 3,789 | 78.3% |
| 2024–25 | 599 | 455 | 4,095 | 76.0% |
| **Total** | **2,916** | **2,265** | **20,385** | **77.7%** |

The database adds three deliberately small tables: `players` (stable official player ID and roster name), `player_team_seasons` (season-team membership), and `individual_matches` (team match, position, both player IDs, winner, game scores, and source URL). Stable Club Locker IDs, rather than names, link players across seasons and transfers. Official rosters name 3,682 of 3,766 players; the remaining 84 retain their unambiguous official ID and a null display name rather than a guessed identity.

Club Locker's historical roster endpoint returns a field named `CurrentRating`, but sampling the same player through different historical team rosters returned the same present-day value. It is therefore not a date-appropriate historical rating and is never imported or used. The research model instead maintains a project-defined player Elo from earlier individual results only. Elo starts at 1500, uses K=20, and carries 75% of its distance from 1500 between seasons. All results on one date are applied as a batch.

### Individual model

The individual logistic regression uses standardized, strictly pre-match differences in player Elo, smoothed win percentage, last-five form, and prior head-to-head, plus lineup position. Evaluation uses the same expanding-season walk-forward design as the team model.

| Held-out season | Training individuals | Test individuals | Accuracy | Log loss | Brier |
|---|---:|---:|---:|---:|---:|
| 2021–22 | 4,653 | 4,131 | 63.4% | 0.627 | 0.219 |
| 2022–23 | 8,784 | 3,717 | 68.5% | 0.586 | 0.201 |
| 2023–24 | 12,501 | 3,789 | 68.7% | 0.584 | 0.201 |
| 2024–25 | 16,290 | 4,095 | 68.1% | 0.582 | 0.200 |
| **Aggregate** | — | **15,732** | **67.1%** | **0.595** | **0.205** |

Player Elo alone reaches 65.7% accuracy, 0.643 log loss, and 0.225 Brier. The logistic model's ten-bin expected calibration error is 0.014 internally. Performance is much weaker for close individual pairings: 60.6% accuracy for an Elo gap under 50, versus 76.2% for 50–99, 89.9% for 100–199, and 97.8% for 200+. Position-level accuracy ranges from 65.4% to 70.9%, with the top position easiest in this sample. These are internal historical results, not evidence of external calibration.

### Nine-player team probability

For each known historical lineup, the model estimates nine individual probabilities. A short exact dynamic program constructs the probability distribution for zero through nine wins. Team win probability is the sum for five through nine; expected score is the sum of the nine individual probabilities. This treats individual outcomes as conditionally independent, an important simplification.

Across 1,748 held-out team matches with complete lineups, the comparison is:

| Method | Accuracy | Log loss | Brier |
|---|---:|---:|---:|
| Pre-match win percentage | 62.0% | 0.646 | 0.228 |
| Team Elo | 70.6% | 0.601 | 0.206 |
| Existing team logistic model | **78.8%** | **0.448** | **0.146** |
| Player-lineup model | 72.0% | 0.531 | 0.179 |

The lineup model does not improve the existing model overall. For 281 first-time program matchups it records 65.8% accuracy, 0.578 log loss, and 0.199 Brier, compared with 66.9%, 0.606, and 0.211 for the team model. That is better probability quality but not better winner selection. For 1,467 repeat matchups, the lineup model reaches 73.1% accuracy versus 81.1% for the team model. It also trails badly on close team-Elo matches (65.8% versus 74.5%) and Elo-defined upsets (34.8% versus 51.4%).

A deliberately simple combined meta-model uses only the earlier out-of-fold team and lineup probabilities. On 1,289 matches from 2022–23 onward it reaches 80.3% accuracy, 0.418 log loss, and 0.133 Brier, versus 80.7%, 0.416, and 0.134 for the team model alone. The tiny Brier improvement does not offset worse accuracy and log loss, so it is not promoted.

Player-level predictions were not promoted as unconditional forecasts and the existing production artifact was not replaced. A future-match lineup forecast requires nine verified or responsibly projected current-season pairings; silently substituting old lineups would fabricate availability. The research outputs remain reproducible CSV/JSON files for inspection.

Manual source checks include official scorecards 136400 (Harvard 8–1 MIT, 2019–20), 167158 (Hobart 6–3 Colby, 2022–23), and 224170 (Denison 6–3 Hobart, 2024–25). In each, positions 1–9 reproduce the team score. The main coverage gaps are incomplete/defaulted lower lineup positions and missing player IDs on otherwise visible rows. Player Elo is sparse for newcomers, lineups are observed rather than forecast, and the nine individual probabilities are not truly independent. The next section revisits the original rating-availability conclusion using the profile archive.

## Historical Club Locker rating research

The earlier conclusion that historical official ratings were unavailable was revised after inspecting the Rankings → Season Rankings archive on player profiles. Club Locker's public endpoint
`https://api.ussquash.com/resources/res/user/{player_id}/rankings?history=yes`
returns the dated archive reproducibly without a login. Raw responses are checkpointed under `data/raw/player_season_rankings/`; the normalized rows retain player ID, ranking period, rating, ranking group, division, source URL, and retrieval time.

Club Locker labels each date `RankingPeriod` and presents weekly snapshots, but neither the response nor the inspected interface documents whether a snapshot published on a match date existed before that match. The project therefore applies the conservative rule: a match on date D can use only the newest snapshot with `RankingPeriod < D`. Same-day and later snapshots are never eligible. When the archive repeats a rating across ranking organizations and divisions, normalization keeps one row per player/date using Universal Squash Rating first, then US Squash, then CSA; all-player/all-gender divisions take priority over age divisions. Ratings are never averaged, interpolated, or filled.

Reproduce the pipeline with:

```bash
python scripts/collect_player_ratings.py
python scripts/build_database.py
python scripts/export_official_ratings.py
python scripts/evaluate_official_ratings.py
```

The collector is checkpointed and skips snapshots already saved. The database adds `player_ratings` and `individual_match_ratings`. The latter records both selected dates, values, rating ages, their difference, and an availability flag. The processed audit files are `historical_player_ratings.csv`, `individual_match_historical_ratings.csv`, and `historical_rating_coverage.csv`.

### Coverage and source validation

The archive produced 1,271,804 canonical weekly snapshots for 3,486 of 3,766 stable player IDs. A valid pre-match rating was available for both players in 18,617 of 20,385 individual matches (91.3%); 1,768 matches remain unavailable and are not imputed. The median selected snapshot was three days old, and the audit found zero same-day selections.

| Season | Rated individuals | All individuals | Coverage |
|---|---:|---:|---:|
| 2019–20 | 3,863 | 4,653 | 83.0% |
| 2021–22 | 3,516 | 4,131 | 85.1% |
| 2022–23 | 3,608 | 3,717 | 97.1% |
| 2023–24 | 3,662 | 3,789 | 96.6% |
| 2024–25 | 3,968 | 4,095 | 96.9% |

Coverage by gender ranges from 82.8%–97.9% and is reported exactly in `historical_rating_coverage.csv`. For a saved October 27, 2023 match, three sampled players were assigned their October 25 snapshots (4.81, 5.36, and 3.76); the raw archive's next rows were November 1 (4.84, 5.34, and 3.81) and were correctly excluded. Unit tests separately prove strict same-day exclusion, newest-prior selection, stable-ID association, and later-season isolation.

### Leakage-safe walk-forward results

Every held-out season is predicted by models trained only on earlier seasons. Project Elo and match-history state still update only after all results on a calendar date have been scored. The official model uses standardized historical rating difference and lineup position. The combined player model adds project player-Elo difference. No held-out-season tuning was performed.

| Individual method | Matches | Accuracy | Log loss | Brier |
|---|---:|---:|---:|---:|
| Project player Elo | 14,754 | 66.0% | 0.641 | 0.225 |
| Official historical rating | 14,754 | **84.9%** | 0.340 | **0.105** |
| Official rating + player Elo | 14,754 | 84.8% | **0.340** | 0.105 |
| Previous full player model | 14,754 | 67.2% | 0.594 | 0.205 |

Official-rating accuracy is 81.7%, 86.4%, 86.0%, and 85.5% across the four held-out seasons. Ten-bin expected calibration error is 0.014 for official rating and 0.011 for official rating plus Elo. Rating difference is the dominant standardized coefficient (3.21–3.74); position is small (0.01–0.07), and player Elo adds only 0.10–0.15. This dominance is plausible because the official rating is specifically designed to summarize player strength, but it also means the result depends heavily on Club Locker's rating methodology and snapshot semantics.

The official model reaches 68.2% accuracy when the absolute rating gap is below 0.25, 92.2% for 0.25–0.49, 98.1% for 0.50–0.99, and 99.4% for 1.00+. Accuracy by lineup position ranges from 83.0% to 85.9%, so the aggregate is not produced by one position alone.

### Nine-player lineup comparison

Only matches with nine observed positions and valid pre-match ratings for all 18 players are included. The exact Poisson-binomial calculation saves team win probability, expected team score, and the full probability distribution for zero through nine wins.

| Method on common 1,281-match subset | Accuracy | Log loss | Brier |
|---|---:|---:|---:|
| Team Elo | 71.7% | 0.597 | 0.204 |
| Existing team logistic model | 79.9% | 0.437 | 0.141 |
| Project player-Elo lineup | 71.9% | 0.592 | 0.202 |
| Official-rating lineup | **92.6%** | 0.193 | **0.060** |
| Official rating + player Elo lineup | 92.0% | **0.194** | 0.060 |
| Previous full player lineup | 72.6% | 0.525 | 0.177 |

The historical-rating lineup is especially useful for the previously weak first-time-team subset: on 174 first meetings it reaches 96.6% accuracy, 0.111 log loss, and 0.034 Brier, versus 68.4%, 0.585, and 0.203 for the existing team model. On 1,107 repeat meetings it reaches 92.0% accuracy versus 81.7% for the existing team model.

A leakage-safe two-input meta-model was also tested from 2022–23 onward. It reaches 92.4% accuracy, 0.200 log loss, and 0.057 Brier, but does not improve on the official-plus-Elo lineup's 92.5%, 0.187, and 0.057 on the same 1,053 matches. It is therefore not justified.

These comparisons use known historical lineups, not forecast future lineups, so they measure the value of player strength conditional on knowing all nine pairings. The production team model remains unchanged. The app exposes prediction-mode readiness but withholds a future estimate until the required current-season evidence exists.

## Prospective lineup projection research

Run the leakage-safe projection backtest with:

```bash
python scripts/evaluate_lineup_projection.py
```

For every historical match, the script acts as if the future lineup is unknown. It creates a projection before reading that day's results, predicts the match using the unchanged official-rating model, and only then adds the actual lineup to team history. Histories reset at each season boundary, and all matches on one date are projected before any lineup from that date becomes available.

The three prediction modes are defined as follows:

1. **Verified lineup:** all nine pairings are supplied from a confirmed source. This is the previously validated 92.6%-accuracy research mode.
2. **Projected lineup:** each team uses its most recent complete lineup from an earlier date in the same season. The display must identify it as projected. Confidence combines recent participation, position stability, and the amount of prior evidence; one prior lineup can contribute at most one-third confidence.
3. **Team-only fallback:** the existing team model is used when either lineup is unavailable, a player lacks a valid pre-match rating, or minimum lineup confidence is below the fixed 0.75 threshold.

The recent-five consensus method and official roster order were also evaluated. Roster order is only a diagnostic: the saved season roster has no historical publication timestamp, so it may reflect later season changes and is not treated as leakage-safe for production decisions.

### Projection accuracy

Across the 1,748 held-out matches with complete actual scorecards, the most-recent-lineup method produced fully rated projections for 1,165 matches (66.6%). On those matches:

| Measure | Result |
|---|---:|
| All nine starters correct for one team | 44.6% |
| All nine starters correct for both teams | 20.9% |
| Average correct players per team | 8.11 of 9 |
| Average correct positions per team | 5.96 of 9 |
| Average missing/replaced players | 0.89 per team |
| Shared players in a different position | 2.15 per team |

Exact position order is substantially less stable than participation. The confidence measure reflects this rather than presenting projected pairings as confirmed. High-confidence projections average 8.30 correct players and 6.52 correct positions; lower-confidence projections average 7.97 and 5.52.

| Model on 1,165 projectable matches | Accuracy | Log loss | Brier |
|---|---:|---:|---:|
| Verified lineup, where available (1,131) | 92.7% | 0.198 | 0.061 |
| Most recent projected lineup | **90.0%** | **0.250** | **0.074** |
| Existing team model | 80.3% | 0.423 | 0.137 |

The projected method remains ahead of the team model in every held-out season, with accuracy of 86.8%, 88.7%, 91.9%, and 91.6%. For 149 projectable first-time matchups it reaches 94.0% accuracy, 0.151 log loss, and 0.048 Brier, compared with 68.5%, 0.575, and 0.199 for the team model. Verified lineups remain better where they are available.

Recent-five consensus covers slightly more matches (67.8%) but is not materially better: 90.2% accuracy, 0.255 log loss, and 0.074 Brier, with fewer correct starters and exact positions. The most recent lineup is retained as the simpler prospective projection. Saved roster order reaches 90.8% on a smaller 883-match subset, but its missing publication timestamps prevent a leakage-safe production claim.

### Fallback policy and deployment decision

Applying the fixed confidence rule across all 1,748 held-out matches uses projected lineups 513 times and the team fallback 1,235 times. The combined policy reaches 82.0% accuracy, 0.390 log loss, and 0.125 Brier, versus 78.8%, 0.448, and 0.146 for team-only prediction. On all 281 first-time matchups it improves accuracy from 66.9% to 73.7%.

The backtest therefore justifies prospective lineup prediction **when recent same-season lineups and current ratings are available**. It does not justify displaying a live projected lineup before verified 2026–27 scorecards exist. The app therefore shows the mode and readiness explanation without showing graduated or unavailable players as likely starters; incremental refreshes can activate the established policy without changing the validated rating model.

Research outputs are saved as `historical_lineup_projections.csv`, `projected_lineup_backtest.csv`, and `projected_lineup_evaluation.json`.

## Untouched 2025–26 external holdout

The completed 2025–26 season was added from the official archived CSA league (league 2200), using dedicated men's varsity division 5733 and women's varsity division 5736. It was not used to change features, decay constants, model settings, or the 0.75 lineup-confidence threshold. Team and player models train only through 2024–25 before scoring this season.

The season adds 621 confirmed team matches: 336 men's and 285 women's. Of these, 450 have a validated nine-position scorecard, producing 4,050 individual matches. Scorecard coverage is 72.5%. The source-validation log excludes 35 schedule rows: 30 not confirmed, one malformed confirmed row, one tied confirmed row, and three matches involving no varsity team. Scorecard validation excludes another 171 team matches because the saved result does not contain nine complete, identity-linked positions that reproduce the team score.

Historical ratings are available for both players in 3,973 of 4,050 individual matches (98.1%): 99.1% for men and 96.7% for women. The strict `rating_date < match_date` rule remains unchanged, and the final audit again finds zero same-day or future assignments.

| Untouched 2025–26 model | Matches | Accuracy | Log loss | Brier |
|---|---:|---:|---:|---:|
| Team model | 621 | 78.4% | 0.447 | 0.144 |
| Verified official-rating lineup | 393 | **89.6%** | **0.230** | **0.073** |
| Projected most-recent lineup | 354 | 85.6% | 0.285 | 0.094 |

Close matches use the existing definition of absolute pre-match team-Elo difference below 100. On that group, the team model reaches 72.6% accuracy, the verified lineup 85.8%, and the projected lineup 81.3%. On repeat matchups the results are 78.4%, 89.5%, and 85.2% respectively.

Only 37 team matches are first-time program pairings under the decayed historical definition. The team model reaches 78.4%. Verified lineups cover 12 and reach 91.7%; projected lineups cover only 10 and happen to win all 10, so the apparent 100% result is reported but not treated as stable evidence.

The external season supports the earlier ordering: historically correct player ratings remain substantially better than the team model, and projected lineups retain much of that advantage. Performance is lower than the earlier five-season internal backtest, especially for projected lineups, so the original 92.6% and 90.0% figures should not be presented as expected live accuracy. The untouched 2025–26 results above are the more conservative prospective reference.

Reproduce the external check with:

```bash
python scripts/collect_season.py 2025-26
python scripts/collect_player_data.py
python scripts/collect_player_ratings.py
python scripts/build_database.py
python scripts/export_official_ratings.py
python scripts/evaluate_lineup_projection.py
python scripts/evaluate_2025_26_holdout.py
```

The final machine-readable report is `data/processed/holdout_2025_26_evaluation.json`.

## Preparing 2026–27 incremental use

`scripts/update_current_season.py` knows the official current men's and women's varsity divisions (6376 and 6379). Each run refreshes current schedules and rosters, saves newly completed scorecards, refreshes full rating histories for active players while archiving the prior snapshots, and writes `data/processed/current_season_readiness.json`.

The script deliberately does not generate predictions. Projected mode stays closed until both teams have at least three earlier complete lineups in 2026–27 and satisfy the unchanged 0.75 confidence rule. Once that gate is met, the existing three-mode policy applies:

1. verified lineup when exact pairings are confirmed;
2. clearly labeled projected lineup when current-season evidence is sufficient;
3. unchanged team-model fallback otherwise.

Run the incremental collector only when a current-season refresh is wanted:

```bash
python scripts/update_current_season.py
```

The current season is intentionally not registered as a completed historical season in the database yet. This prevents scheduled or sparse early-season data from silently entering model evaluation or triggering irresponsible 2026–27 forecasts.

## Live-season refresh

Run one incremental refresh from the project root:

```bash
python scripts/update_current_season.py
```

The command checks the two official 2026–27 schedules, preserves stable source match IDs, archives changed roster/rating/scorecard snapshots, downloads only new or source-changed scorecards, and refreshes a rating history only when the official roster rating differs from the saved history. Complete scorecards must contain positions 1–9 exactly once and reproduce the team score. Incomplete scorecards are logged and never become verified lineups.

Database changes are applied to a copy of SQLite, validated, and atomically replace the live file only after the whole update succeeds. The production models are never fitted or overwritten. Their live metadata is `official-rating-logistic-v1`, trained through 2025–26 with feature version `official-rating-difference-position-v1`.

Prediction mode is decided in the backend: verified pairings when supplied; otherwise the validated current-season projection after both teams have at least three earlier complete lineups and confidence of at least 0.75; otherwise preseason projection; then team-only fallback or unavailable. The frontend only renders that decision. Refreshes also create immutable snapshots for eligible fixtures in the next 14 days. After results arrive, run `python scripts/evaluate_live_predictions.py` to calculate accuracy, log loss, and Brier score separately by stored mode. Small samples should not be presented as headline performance.

`GET /api/status` reports freshness, scheduled/completed counts, scorecard and lineup readiness, warnings, and frozen model metadata. For offline validation using existing files, run `python scripts/update_current_season.py --from-cache`.

SQLite remains appropriate for local single-writer updates. A public deployment may serve a read-only SQLite copy, but an updater running in deployment requires a persistent writable disk and single-writer coordination. Multi-instance or ephemeral hosting will eventually require persistent object storage plus a database such as PostgreSQL; this milestone does not perform that migration.

## Prediction presentation and interface audit

The Rochester–MIT preseason projection was independently recomputed from all nine pairing probabilities. Rochester's expected score is 1.8190 wins and its exact probability of winning at least five positions is 0.321168%; MIT's complementary probability is 99.678832%. Reversing the teams preserves complementary player and team probabilities. The audit found no model calculation or team-orientation error.

The interface now keeps raw probabilities unchanged while bounding only the displayed values to 0.1%–99.9%, so an extreme estimate is not rendered as certain. Matchup tables state which team's individual probability is shown. Rankings can be sorted by rank, record, Elo, win percentage, strength of schedule, or scoring margin. Player pages include official-rating chart axes and exact-value tooltips, linked current-team context, and linked opponent/player history with readable game scores.

## Public read-only deployment

The public configuration keeps the existing FastAPI and Next.js applications and serves the checked, read-only SQLite snapshot. It does not run the live updater remotely. Local refreshes produce a newly validated snapshot that can be included in a later deployment.

The complete manual release procedure and hosting configuration are in [`DEPLOYMENT.md`](DEPLOYMENT.md).

Copy `.env.example` to `.env` for local development. The relevant settings are:

- `DATABASE_PATH`: SQLite snapshot used by FastAPI.
- `DATABASE_READ_ONLY`: use `1` in public deployments so SQLite opens in read-only mode.
- `CORS_ORIGINS`: comma-separated browser origins allowed to call the API. Set the exact frontend origin in production; do not use `*`.
- `DEPLOYMENT_ENV`: descriptive environment name for hosting configuration.
- `NEXT_PUBLIC_API_BASE_URL`: public FastAPI origin embedded in the frontend production build.

Start the backend locally:

```bash
PYTHONPATH=src uvicorn college_squash.api:app --host 127.0.0.1 --port 8000
```

Start the frontend locally:

```bash
cd frontend
npm install
npm run dev
```

Production backend startup:

```bash
PYTHONPATH=src uvicorn college_squash.api:app --host 0.0.0.0 --port $PORT
```

Build and start the frontend after setting `NEXT_PUBLIC_API_BASE_URL`:

```bash
cd frontend
npm ci
npm run build
npm start
```

The root Dockerfile expands the tracked 27 MB `data/college_squash.db.gz` artifact into the read-only runtime snapshot. The root and frontend Dockerfiles package only application code, API-only dependencies, frozen models, the database snapshot, and required freshness metadata. Raw Club Locker archives, processed training exports, caches, virtual environments, Streamlit-only dependencies, and frontend build output are excluded. `/api/health` is intentionally lightweight; `/api/status` provides refresh and prediction-readiness details without running model inference.

### Short-handed lineup policy

The prospective lineup policy follows the CSA minimum-team rule: nine or more rated eligible players produce a normal lineup, eight produce one bottom-position forfeit, seven produce two, and fewer than seven use the team-only fallback when it is available. Forfeits have no invented player or rating and are deterministic 0/1 inputs only when calculating the prospective team probability. They are never added to model training or historical evaluation. The interface retains the 0.1%/99.9% presentation bounds.

### What-if lineup scenarios

Match and Compare pages can temporarily reorder or substitute current official-roster players and model legal seven-, eight-, or nine-player scenarios. The browser sends nine explicit player/forfeit slots to `POST /api/compare/custom-lineup`; FastAPI validates team membership, uniqueness, bottom-position forfeits, the seven-player minimum, and current-rating availability before using the unchanged player model. The response includes individual probabilities, expected wins, exact team probability, and the full zero-through-nine win distribution. Scenarios exist only in browser state and never update SQLite, the stored projection, historical results, or model artifacts. Because the project does not encode all CSA order-of-play legality rules, the interface deliberately labels these as what-if scenarios rather than official lineup builders.

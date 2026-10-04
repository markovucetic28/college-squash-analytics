# College Squash Analytics

College Squash Analytics is a data and machine learning project I built to explore college squash results, analyze player and team performance, and predict match outcomes.

It combines historical match data, player ratings, rosters, and lineups into a public web app with rankings, team and player pages, schedules, head-to-head comparisons, and matchup predictions.

**Live site:** https://college-squash-analytics.vercel.app

**Tech:** Python, pandas, scikit-learn, SQLite, FastAPI, Next.js, TypeScript

---

## What it does

The project includes:

- Team and player profiles
- Historical match results
- Player rating history
- Men's and women's rankings
- Current schedules
- Head-to-head comparisons
- Individual matchup probabilities
- Team match predictions using projected or verified lineups

The dataset currently includes more than:

- **24,000 individual matches**
- **3,500 team matches**
- **6 seasons of college squash data**

Most of the data comes from public College Squash Association / Club Locker sources.

---

## Prediction system

### Individual match predictions

The production player model estimates win probability using pre-match player information, mainly historical player ratings and lineup context.

One of the main challenges was avoiding data leakage. For historical evaluation, each prediction only uses information that would have been available before the match was played.

On held-out historical data, the production individual model achieved approximately:

- **85% accuracy**
- **0.340 log loss**
- **0.105 Brier score**

I also built research models that test recent performance, point dominance, close-match behavior, and calibration without changing the live production model.

### Team match predictions

For projected or verified lineups, the system predicts all nine individual positions and combines those probabilities using an exact **Poisson-binomial calculation**.

This produces:

- Team win probability
- Expected number of wins
- Individual position probabilities
- Full probability distribution for possible 0–9 team scores

On historical matches with verified lineups, the lineup-based model reached about **92.6% accuracy**.

On the untouched 2025–26 season, verified-lineup predictions reached about **89.6% accuracy**.

---

## Model validation

A big focus of the project was making sure the evaluation was realistic.

The modeling pipeline uses:

- Walk-forward validation
- Strict pre-match feature construction
- Historical rating timestamps
- Held-out seasons
- Accuracy, log loss, and Brier score
- Probability calibration checks
- Close-match analysis
- Prospective shadow-model evaluation

More detailed model experiments and results are documented in:

[`docs/RESEARCH.md`](docs/RESEARCH.md)

---

## Tech stack

### Data / Machine Learning

- Python
- pandas
- scikit-learn
- SQLite

### Backend

- FastAPI
- Uvicorn

### Frontend

- Next.js
- React
- TypeScript

### Deployment

- Docker
- Railway
- Vercel
- Git / GitHub

---
## Notes

This is an independent project and is not affiliated with the College Squash Association or Club Locker.

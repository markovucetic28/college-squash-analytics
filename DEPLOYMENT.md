# First public deployment checklist

This release is read-only. The validated SQLite snapshot is baked into the backend image; the live-season updater continues to run locally and is not started by either Dockerfile.

## Artifacts included in Git

- `data/college_squash.db.gz` — compressed deployment snapshot; the Docker build expands it to `/app/data/college_squash.db`.
- `data/preseason_player_model.joblib` and `data/matchup_model.joblib` — frozen validated models.
- `data/processed/current_season_readiness.json` — small freshness metadata used by the API.
- `src`, `frontend`, requirements files, Dockerfiles, tests, and documentation.

Raw Club Locker archives, intermediate analysis exports, the uncompressed 283 MB working database, environments, caches, and build output remain local and are ignored.

## Runtime variables

Backend:

```text
DATABASE_PATH=/app/data/college_squash.db
DATABASE_READ_ONLY=1
DEPLOYMENT_ENV=production
CORS_ORIGINS=https://your-vercel-project.vercel.app
```

Frontend build:

```text
NEXT_PUBLIC_API_BASE_URL=https://your-backend.example.com
```

`NEXT_PUBLIC_API_BASE_URL` is embedded at build time. Rebuild the frontend after changing it. Use exact comma-separated origins for `CORS_ORIGINS`; never use `*` in production.

## Commands

Backend without Docker:

```bash
PYTHONPATH=src uvicorn college_squash.api:app --host 0.0.0.0 --port $PORT
```

Backend image:

```bash
docker build -t college-squash-api .
docker run --rm -p 8000:8000 -e PORT=8000 \
  -e DATABASE_READ_ONLY=1 -e DEPLOYMENT_ENV=production \
  -e CORS_ORIGINS=http://localhost:3000 college-squash-api
```

Frontend production build:

```bash
cd frontend
NEXT_PUBLIC_API_BASE_URL=https://your-backend.example.com npm run build
```

Frontend image:

```bash
docker build --build-arg NEXT_PUBLIC_API_BASE_URL=https://your-backend.example.com \
  -t college-squash-web .
```

## Recommended first hosts

- Frontend: Vercel, using the `frontend` directory as the project root.
- Backend: Railway Hobby for the first public release. It supports repository and Dockerfile deployment, environment variables, health checks, and a baked read-only SQLite file. The current plan has a $5 monthly minimum including $5 of usage. No volume is required while the database remains read-only.
- Alternative backend: Render. Its Docker support is straightforward. The free service is suitable for previewing but spins down after inactivity; use the paid starter service for a public site where cold-start delays are undesirable.

## Manual release sequence

1. Review `git add --dry-run .`; confirm no `.env`, raw data, caches, or uncompressed database appears.
2. Create an empty GitHub repository manually. Do not initialize it with conflicting files.
3. Commit locally, add the GitHub remote, and push `main`.
4. In Railway, create a service from the repository and select the root `Dockerfile`.
5. Set the four backend variables above. Initially set `CORS_ORIGINS` to the expected Vercel origin; update it after Vercel assigns the final URL.
6. Set the health-check path to `/api/health`, deploy, then verify `/api/health` and `/api/status` publicly.
7. In Vercel, import the same repository and set the root directory to `frontend`.
8. Set `NEXT_PUBLIC_API_BASE_URL` to the public Railway origin and deploy.
9. Update Railway `CORS_ORIGINS` to the exact production Vercel origin and redeploy/restart the backend if required.
10. Verify `/schedule`, `/rankings`, `/teams`, one team page, and one player page.
11. Search for a current player and a current team.
12. Open a scheduled matchup and confirm its projection loads.
13. Open Compare and confirm an arbitrary same-division comparison loads.
14. Enter What-if mode, reorder one player, substitute one official-roster player, confirm the probability changes, and reset the lineup.
15. Confirm browser developer tools show no CORS or API errors.

Do not run `scripts/update_current_season.py` on either public host. Publish a newly validated compressed snapshot in a later controlled deployment when current-season data changes.

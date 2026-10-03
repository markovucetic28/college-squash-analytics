FROM python:3.11-slim

WORKDIR /app
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt
COPY src ./src
COPY data/college_squash.db.gz data/preseason_player_model.joblib data/matchup_model.joblib ./data/
COPY data/processed/current_season_readiness.json ./data/processed/current_season_readiness.json
RUN gzip -d /app/data/college_squash.db.gz
RUN groupadd --system app && useradd --system --gid app app && chown -R app:app /app

ENV PYTHONPATH=/app/src
ENV DATABASE_PATH=/app/data/college_squash.db
ENV DATABASE_READ_ONLY=1
USER app
EXPOSE 8000
CMD ["sh", "-c", "uvicorn college_squash.api:app --host 0.0.0.0 --port ${PORT:-8000}"]

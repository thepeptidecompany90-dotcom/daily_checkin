# glp1-agent

## Local development

1. Copy `.env.example` to `.env` and fill in real values.

2. Start the local Postgres:

   ```
   docker compose up -d
   ```

   On first boot (empty volume) Postgres automatically applies every file in
   `src/glp1_agent/db/migrations/` — no manual migration step needed.

3. If you add a new migration file later, `docker-entrypoint-initdb.d` won't re-run against an
   existing volume. Reset with:

   ```
   docker compose down -v && docker compose up -d
   ```

   Or apply migrations manually against any Postgres (e.g. one not managed by this compose file):

   ```
   uv run python -m glp1_agent.db.migrate
   ```

4. Run the bot (WebRTC only for now):

   ```
   uv run python3 -m glp1_agent.bot --transport webrtc
   ```

   Requires a `GLP1_PATIENT_ID` env var pointing at an existing row in `patients` — real call
   dispatch isn't wired up yet (V1 placeholder, see `bot.py`).

## Dashboard

```
uv run python -m glp1_agent.dashboard.app
```

Serves a read-only patient dashboard at `http://127.0.0.1:8090` — a patient list, and per-patient
present state (journey/medication) plus what got extracted from their most recent completed
check-in call. Unauthenticated, local-dev only. Independent process from `bot.py`; both read the
same Postgres.

## Tests

```
uv run pytest -q
```

Spins up its own isolated Postgres via testcontainers — independent of the `docker compose` setup
above.

# Local Dev Database And API Workflow Summary

This note captures the setup clarification from the database/API workflow discussion so the project has a durable reference point.

## What We Confirmed

There are three distinct database targets in this project:

1. Legacy native local Postgres
   - Host: `localhost`
   - Port: `5432`
   - This was the original non-Docker local database.
   - In pgAdmin this appeared under `localhost`.
   - It no longer contains anything worth preserving.

2. Local Docker/PostGIS development database
   - Host machine access: `localhost:5433`
   - Container-internal access: `db:5432`
   - This is the database exposed by `docker-compose.yml` via `5433:5432`.
   - In pgAdmin this appeared under `NPS Hikes Docker`.
   - This is the database containing the newer RAG/semantic-search tables such as:
     - `nps_places`
     - `nps_thingstodo`
     - `content_embeddings`

3. Neon production database
   - Remote hosted Postgres
   - Used for deployed/prod-style data workflows
   - Should not be the default local development target

## Important Port Clarification

The `5432` inside `docker-compose.yml` is not the old native local database.

This line:

```yaml
ports:
  - "5433:5432"
```

means:

- `5433` is the port on the Mac host
- `5432` is the port inside the Docker container

So both of these are true at the same time:

- local scripts should connect to the Docker DB on `localhost:5433`
- the Docker API container should connect to the same DB on `db:5432`

## Difference Between `make up` And `make dev`

These commands are different mainly in where the API runs, not which data they use.

### `make up`

- Runs both the database and API in Docker
- Docker DB is available to the host on `localhost:5433`
- Docker API is exposed on `localhost:8000`
- Inside Docker, the API connects to the DB at `db:5432`

### `make dev`

- Runs the API locally on the host machine
- API is exposed on `localhost:8001`
- The local API connects to the same Docker DB via `localhost:5433`
- This is the better day-to-day development workflow because it gives:
  - `uvicorn --reload`
  - easier debugging
  - host-native logs/tracebacks
  - easier Ollama access for NLQ/RAG work

## What Testing Confirmed

We confirmed the following:

- Port `5433` contains the newer Docker-backed development data
- `content_embeddings` exists on `5433` and not on `5432`
- The Docker API on `8000` can read from the Docker DB
- `8000` stops responding if only the DB container is started, which is expected
- `8001` works when `make dev` is running, also against the Docker DB

Important note:

- `8000` and `8001` can both work at the same time, but only if both API processes are running
- if only `docker compose up db -d` is running, then `8000` should fail because the Docker API container is not running

## Decision

The agreed local development direction is:

- Keep the Docker/PostGIS database on `localhost:5433` as the only local development database
- Treat the native local Postgres on `localhost:5432` as legacy and removable
- Use `make dev` as the recommended day-to-day development workflow
- Use `make up` when verifying the full containerized stack
- Treat Neon as production/staging, not the default local target

## Repo Changes Made From This Clarification

The workflow documentation/config was updated to reflect the decision above:

- `.env.example` now points local scripts at `localhost:5433`
- `Makefile` help text now frames:
  - `make dev` as the recommended development path
  - `make up` as the full container-stack path
- `docs/getting-started.md` now explains:
  - the shared Docker DB
  - the difference between `8000` and `8001`
  - the recommended local workflow
- `README.md` and `streamlit_app/README.md` were updated for consistency

## Follow-Up

The old native local Postgres database `nps_hikes_db` on `localhost:5432` can be dropped safely if desired, as long as commands are pointed at port `5433` and not `5432`.

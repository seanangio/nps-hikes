# Automating Profiling: Open Questions and Direction

This is not a final implementation plan yet. It is a summary of the current thinking, the confusion we uncovered, and the decision points that should be resolved before adding GitHub Actions automation.

## Original Idea

The initial idea was to automatically run the profiling modules in `profiling/` whenever files in `raw_data/` change.

The motivating example was the national park visit map:

- update `raw_data/park_visit_log.csv`
- run the data pipeline
- regenerate profiling outputs
- get a fresh `us_park_map_static.png`

That idea still seems reasonable, but the details are more subtle than expected.

## What The Profiling Modules Are

The profiling modules are mostly descriptive reporting modules, not pipeline gates.

They generate:

- summary CSVs
- coverage reports
- matching summaries
- freshness reports
- static images
- interactive HTML visualizations
- per-park elevation/profile outputs

They should not currently fail the data pipeline based on data quality thresholds. Some modules have names like `data_quality`, but in practice they produce descriptive outputs rather than pass/fail assertions.

Actual quality gates could be a separate future task, but that is out of scope for now.

## Important Discovery: Profiling Uses Whatever DB The Environment Points To

`profiling/orchestrator.py` calls `load_dotenv()` and then modules use `get_db_connection()` from `profiling/utils.py`.

That connection goes through `config.settings`, which reads:

- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_SSLMODE`

So profiling does not read directly from `raw_data/`. It reads from Postgres.

This means the profiling output depends entirely on which database the current shell environment points at.

## The Database Confusion

There are several possible database targets:

1. Plain local `.env`
   - currently points to `localhost:5432`
   - this had 62 parks and 36 visited parks

2. Docker/local dev DB
   - `make dev` overrides to `localhost:5433`
   - this is intended to connect to the Docker PostGIS DB
   - at the time of investigation, port `5433` was not accepting connections

3. Neon production DB
   - loaded from `.env.neon`
   - this had 62 parks and 42 visited parks
   - this matched the live demo data

This explains why running:

```bash
python profiling/orchestrator.py
```

could report success while still producing a stale `us_park_map_static.png`: it was successfully profiling the local `localhost:5432` database, not Neon.

The command that generated the map from Neon data was:

```bash
env $(grep -v '^#' .env.neon | xargs) python profiling/orchestrator.py us_park_map
```

## Another Important Discovery: Visualization Endpoints Serve Files

The API endpoint:

```text
/parks/viz/us-static-park-map
```

does not dynamically query the database.

It serves this generated file:

```text
profiling_results/visualizations/us_park_map/us_park_map_static.png
```

So the API can have fresh `/parks` query results while the visualization endpoint remains stale. The map endpoint only updates when the profiling module regenerates the PNG against the correct database.

## Where Generated Files Live

If profiling runs locally, outputs live in local `profiling_results/`.

If profiling runs in GitHub Actions, outputs would live on the temporary GitHub Actions runner unless explicitly preserved.

Possible preservation options:

- upload `profiling_results/` as a GitHub Actions artifact
- commit selected generated outputs
- publish selected outputs to docs/GitHub Pages
- publish outputs to external object storage
- surface selected outputs in the Streamlit app

The files do not go into Neon unless code is written to store them there.

## Gitignore And Repo Size

`profiling_results/*` is gitignored.

This is probably good. The local directory is already fairly large, with most of the size coming from visualizations. Committing the whole generated tree would likely create noisy diffs and repository bloat.

There is one special case: `docs/api-tutorial.md` references a static national map image in `docs/_img/us-park-map-static.png`. That image is currently separate from `profiling_results/`.

Possible approaches:

- keep copying the generated map into `docs/_img/`
- point docs at a published profiling artifact/location
- make docs generation copy selected profiling outputs into a docs-visible directory

## CI Automation Options

### Option 1: GitHub Actions Artifact Only

Run profiling after `deploy-data.yml` and upload the full `profiling_results/` directory as an artifact.

Pros:

- simple
- no repo bloat
- keeps all profiling output available after each run

Cons:

- awkward to browse
- artifacts may expire
- not a good user-facing experience

### Option 2: Commit Selected Outputs

Keep `profiling_results/` ignored, but copy a few selected files into tracked locations such as `docs/_img/`.

Pros:

- solves the national map freshness problem
- keeps docs current
- avoids committing the whole output tree

Cons:

- only handles selected outputs
- still creates binary diffs for images
- needs clear rules for what gets copied

### Option 3: Publish A Static Profiling Page

Generate profiling outputs in CI, then publish a curated subset to the docs site or GitHub Pages.

Pros:

- more browseable
- avoids making GitHub Actions artifacts the main interface
- fits a portfolio/project documentation workflow

Cons:

- requires deciding what should be public
- requires some docs/dashboard structure
- may still involve committing or deploying generated static files

### Option 4: Streamlit Profiling/Admin View

Expose selected profiling information in the Streamlit app.

Pros:

- best user experience if the app is the main surface
- can query live database state directly
- avoids relying only on generated CSV/PNG artifacts

Cons:

- larger app feature
- may blur app/product features with maintainer/admin tooling
- generated images still need a storage/update story

### Option 5: External Object Storage

Run profiling in CI and upload the generated bundle to S3, R2, GCS, or similar.

Pros:

- durable storage without repo bloat
- can keep a latest bundle and historical bundles
- works well for large generated files

Cons:

- extra infrastructure
- probably overkill for now

## CI-Safety Issues

Not every enabled module is clearly CI-safe as-is.

Potential issues:

- `trail_3d_viz` defaults to an interactive prompt unless given a park and trail
- `tnm_hikes.py` exists but does not appear to be included in `PROFILING_MODULES`
- `data_freshness` prints a report but does not currently save structured outputs like the other modules
- output paths are not fully consistent; some modules write flat files and others write nested files

Before running all profiling modules in CI, it may be worth defining an explicit CI-safe profiling suite.

## Possible Makefile Improvements

The current ambiguity could be reduced with explicit targets:

```make
profile-local:
	POSTGRES_HOST=localhost POSTGRES_PORT=5433 python profiling/orchestrator.py

profile-neon:
	env $$(grep -v '^#' .env.neon | xargs) python profiling/orchestrator.py

profile-map-neon:
	env $$(grep -v '^#' .env.neon | xargs) python profiling/orchestrator.py us_park_map
```

The key idea is to stop relying on the default `.env` database target when the desired source of truth is different.

## Possible Code Improvements

Helpful improvements before automation:

- log the active database target at the start of profiling, without printing passwords
- add a `--env-file` or `--database-profile` option to the profiling orchestrator
- add a `--ci` mode or configured CI module list
- make `trail_3d_viz` noninteractive when called by the orchestrator
- make `data_freshness` write CSV/JSON outputs
- create a `profiling_results/manifest.json` with:
  - run timestamp
  - database target
  - modules run
  - successful modules
  - failed modules
  - generated file counts

## Current Leaning

The best near-term path seems to be:

1. Make it explicit whether profiling should read from local Docker DB or Neon.
2. Add Makefile targets for local and Neon profiling.
3. Add logging so profiling states which DB it is using.
4. Keep `profiling_results/` gitignored.
5. For CI, eventually run profiling after `deploy-data.yml` against Neon.
6. Preserve the full output as a GitHub Actions artifact.
7. Publish only a small curated subset, probably starting with the national park map.

This keeps the automation useful without pretending the profiling system is a mature data quality gate or committing a large generated artifact tree.

## Open Questions

- Should Neon be considered the source of truth for profiling?
- Should local profiling default to Docker DB on `localhost:5433` instead of `.env`?
- Should the docs map be copied from profiling output, or should docs link to a published profiling location?
- Which profiling outputs are actually worth publishing?
- Should there be a lightweight profiling dashboard?
- Should generated profiling artifacts be retained historically, or is only the latest run useful?
- Should CI run all modules or only a curated CI-safe subset?
- Should visualization endpoints serve generated files, or generate/query dynamically in the future?

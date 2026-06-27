# RAG Implementation Plan: Semantic Search for NPS Hikes

## Overview

Add retrieval-augmented generation (RAG) to the NPS Hikes project by:

1. Collecting rich text content from two new NPS API endpoints (`/thingstodo`, `/places`)
2. Storing raw content in PostgreSQL and embedding it as vectors via pgvector
3. Exposing semantic search through a standalone `/search` API endpoint
4. Integrating semantic search as a new tool in the existing NLQ system

All embeddings are generated locally via Ollama (`nomic-embed-text`), keeping everything free and consistent with the existing stack.

---

## Implementation Status

All code has been written and verified end-to-end. **423 unit tests pass.** The full pipeline has been run against all 62 parks, producing 10,465 embeddings. The `/search` endpoint and NLQ integration have been manually tested.

| Step | Status | Notes |
|------|--------|-------|
| Step 1: Docker & DB Infrastructure | **Verified** | pgvector + PostGIS image builds, extensions load, schema creates correctly |
| Step 2: NPS Content Collector | **Verified** | Collected 6,771 content records across 62 parks |
| Step 3: Chunking & Embedding Pipeline | **Verified** | 10,465 chunks embedded and stored |
| Step 4: Standalone /search Endpoint | **Verified** | Returns ranked results with similarity scores |
| Step 5: NLQ Integration | **Verified** | `search_park_content` tool dispatches correctly |
| Step 6: Unit Tests | **All 423 passing** | 54 new + 3 updated existing tests |
| Step 7: Orchestrator | **Verified** | All 8 pipeline steps complete successfully |
| Step 8: Code Review | **Passed** | All 9 checklist items reviewed |
| Integration tests (7g) | **Not written** | Deferred |

### Bugs found and fixed during verification

| Bug | Root cause | Fix |
|-----|-----------|-----|
| `pd.isna()` crash on list columns | `pd.isna(v)` returns an array when `v` is a list, which can't be used in `if` | Check `isinstance(v, (list, dict))` before calling `pd.isna()` in `write_thingstodo()` and `write_places()` |
| SQL syntax error on `::vector` cast | SQLAlchemy `text()` interprets `:embedding` as a bind param, then `::vector` is garbled | Changed to `CAST(:embedding AS vector)` in `db_writer.py` and `queries.py` |
| Embedding indexer rejects `--write-db` | Orchestrator passes `--write-db` to all steps, but indexer didn't accept it | Added `--write-db` as accepted no-op argument |
| Duplicate embeddings on re-run | `index_all()` appended without truncating, so each run doubled the data | Changed to always truncate `content_embeddings` before re-indexing |
| Oversized chunks crash Ollama | Some NPS places have very long body text without paragraph breaks, exceeding model context | Added sentence-boundary splitting in `_split_text()` for paragraphs over `MAX_CHUNK_LENGTH` |

---

## Decisions Made

| Decision | Choice |
|----------|--------|
| NPS endpoints | `/thingstodo` and `/places` (Tier 1 only) |
| Vector database | pgvector (extension in PostgreSQL) |
| Embedding model | `nomic-embed-text` via Ollama `/api/embed` |
| Docker image | Switch to `pgvector/pgvector:pg16` + install PostGIS |
| DB migration | Add to `init-db.sh` (no migration script needed, solo project) |
| API surface | Both standalone `/search` endpoint + NLQ tool |
| Data refresh | Not needed yet; one-time collection is sufficient |
| Embedding client location | `utils/embedding_client.py` (shared by both `api/` and `scripts/`, same pattern as `utils/logging.py`) |
| Vector column writes | `CAST(:param AS vector)` via SQLAlchemy `text()` (no `pgvector` Python package — consistent with existing `db_writer.py` raw SQL pattern) |
| LLM answer generation | Deferred — not in this plan (see below) |
| Streamlit UI | Deferred — not in this plan (see below) |

---

## Files Changed

### New files (11):

| File | Purpose |
|------|---------|
| `docker/Dockerfile.db` | Custom DB image: pgvector base + PostGIS installed on top |
| `sql/schema/nps_content.sql` | Schema for `nps_thingstodo`, `nps_places`, `content_embeddings` (with HNSW index) |
| `scripts/collectors/nps_content_schemas.py` | Pydantic schemas for `/thingstodo` and `/places` responses with HTML stripping |
| `scripts/collectors/nps_content_collector.py` | Collector class: fetches content per-park with pagination, retry, resumability |
| `scripts/processors/text_chunker.py` | Text chunking: paragraph-boundary splitting at ~2000 chars |
| `scripts/processors/embedding_indexer.py` | Full pipeline: load content → chunk → embed via Ollama → write to pgvector |
| `utils/embedding_client.py` | Ollama `/api/embed` wrapper (async + sync versions) |
| `tests/unit/test_nps_content_collector.py` | 10 collector unit tests |
| `tests/unit/test_nps_content_schemas.py` | 17 schema validation tests |
| `tests/unit/test_text_chunker.py` | 9 chunker unit tests |
| `tests/unit/test_embedding_client.py` | 10 embedding client unit tests (async uses `asyncio.run()`) |

### Modified files (12):

| File | Changes |
|------|---------|
| `docker-compose.yml` | `db` service: `image:` → `build:` pointing at `docker/Dockerfile.db` |
| `docker/init-db.sh` | Added `CREATE EXTENSION IF NOT EXISTS vector;` + `nps_content.sql` to schema load loop |
| `config/settings.py` | 12 new config entries for content collection + embedding settings |
| `utils/logging.py` | Added `setup_nps_content_collector_logging()` + `setup_embedding_indexer_logging()` |
| `scripts/database/db_writer.py` | Added 3 tables to `table_dependencies`, `drop_all_tables`, `ensure_table_exists`; added `write_thingstodo()`, `write_places()`, `write_embeddings()`, `_create_nps_content_tables()` |
| `scripts/orchestrator.py` | Added "NPS Content Collection" (after NPS Data Collection) + "Content Embedding" (at end) |
| `api/main.py` | Added `GET /search` endpoint; added `search_park_content` dispatch in `POST /query`; added `/search` to root endpoint listing |
| `api/models.py` | Added `SearchResult` + `SearchResponse` Pydantic models |
| `api/queries.py` | Added `fetch_semantic_search()` using pgvector `<=>` cosine distance |
| `api/nlq/prompt.py` | Added `search_park_content` tool definition; updated system message guidance |
| `api/nlq/parser.py` | Added `search_park_content` to `VALID_FUNCTIONS`; added `_normalize_content_search_params()` |
| `tests/conftest.py` | Added 4 fixtures: `sample_thingstodo_api_response`, `sample_places_api_response`, `sample_embedding_vector`, `content_collector` |
| `tests/unit/test_nlq_prompt.py` | Updated tool count assertion (4→5); added 3 content tool tests; updated optional-params test |
| `tests/unit/test_nlq_parser.py` | Added 7 `search_park_content` normalization tests |

---

## Next Steps: Verification Checklist

Work through these in order. Each step depends on the previous one succeeding.

### 1. Rebuild Docker container

Rebuild the database from scratch with the new pgvector + PostGIS image and schema:

```bash
docker compose down -v && docker compose up --build -d
```

**Verify:**
- Container starts healthy: `docker compose ps` (should show `healthy`)
- Extensions exist: `docker compose exec db psql -U seanangiolillo -d nps_hikes_db -c "\dx"` — should list `postgis`, `pg_trgm`, and `vector`
- Tables exist: `docker compose exec db psql -U seanangiolillo -d nps_hikes_db -c "\dt"` — should include `nps_thingstodo`, `nps_places`, `content_embeddings`
- Vector column exists: `docker compose exec db psql -U seanangiolillo -d nps_hikes_db -c "\d content_embeddings"` — should show `embedding vector(768)`

### 2. Populate base park data

The content collector needs parks in the database first. Run the existing NPS collector for 1 park:

```bash
source ~/.virtualenvs/nps-hikes/bin/activate
POSTGRES_HOST=localhost POSTGRES_PORT=5433 python scripts/collectors/nps_collector.py --test-limit 1 --write-db
```

**Verify:** `docker compose exec db psql -U seanangiolillo -d nps_hikes_db -c "SELECT count(*) FROM parks;"` returns ≥ 1.

### 3. Run the content collector

Collect thingstodo + places for the test park(s):

```bash
POSTGRES_HOST=localhost POSTGRES_PORT=5433 python scripts/collectors/nps_content_collector.py --test-limit 1 --write-db --log-level DEBUG
```

**Verify:**
- Check log output for `"Collected N thingstodo and M places for <park_code> (1/1)"`
- Data in DB:
  ```bash
  docker compose exec db psql -U seanangiolillo -d nps_hikes_db -c "SELECT count(*) FROM nps_thingstodo;"
  docker compose exec db psql -U seanangiolillo -d nps_hikes_db -c "SELECT count(*) FROM nps_places;"
  docker compose exec db psql -U seanangiolillo -d nps_hikes_db -c "SELECT park_code, title FROM nps_thingstodo LIMIT 3;"
  ```
- CSV artifacts saved: `ls artifacts/nps_*_collected.csv`

### 4. Pull the embedding model

```bash
ollama pull nomic-embed-text
```

**Verify:** `ollama list` shows `nomic-embed-text`.

### 5. Run the embedding indexer

```bash
POSTGRES_HOST=localhost POSTGRES_PORT=5433 python scripts/processors/embedding_indexer.py --log-level DEBUG
```

**Verify:**
- Log output shows chunk counts and batch progress
- Embeddings in DB:
  ```bash
  docker compose exec db psql -U seanangiolillo -d nps_hikes_db -c "SELECT count(*) FROM content_embeddings;"
  docker compose exec db psql -U seanangiolillo -d nps_hikes_db -c "SELECT source_type, count(*) FROM content_embeddings GROUP BY source_type;"
  docker compose exec db psql -U seanangiolillo -d nps_hikes_db -c "SELECT title, source_type, length(chunk_text) FROM content_embeddings LIMIT 5;"
  ```

### 6. Test the /search endpoint

Start the API server (if not already running via docker compose):

```bash
POSTGRES_HOST=localhost POSTGRES_PORT=5433 uvicorn api.main:app --port 8001 --reload
```

Test semantic search:

```bash
curl -s "http://localhost:8001/search?q=waterfalls" | python -m json.tool
curl -s "http://localhost:8001/search?q=winter+activities&limit=3" | python -m json.tool
```

**Verify:**
- Response includes `query`, `result_count`, and `results` array
- Each result has `chunk_text`, `similarity_score`, `park_code`, `source_type`
- Scores are between 0 and 1, ordered descending
- Check the interactive docs page at `http://localhost:8001/docs` — `/search` should appear under the "Search" tag

### 7. Test the NLQ integration

With Ollama running (`ollama serve`):

```bash
curl -s -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{"query": "things to do in winter at Yosemite"}' | python -m json.tool
```

**Verify:**
- Response has `function_called: "search_park_content"`
- `results` contains semantic search results (not trail/park structured data)
- Also try a regular trail query to make sure existing NLQ still works:
  ```bash
  curl -s -X POST http://localhost:8001/query \
    -H "Content-Type: application/json" \
    -d '{"query": "longest trails in Yosemite"}' | python -m json.tool
  ```

### 8. Run the full unit test suite

```bash
python -m pytest tests/unit/ -v
```

**Verify:** All 423 tests pass (already confirmed, but re-run after any manual changes).

### 9. Code review checklist

Spot-check these files for correctness:

- [ ] `docker/Dockerfile.db` — does `postgresql-16-postgis-3` match the pgvector base image's PG version?
- [ ] `sql/schema/nps_content.sql` — are FK constraints, CHECK constraints, and indexes correct?
- [ ] `scripts/database/db_writer.py` — do `write_thingstodo()` and `write_places()` handle JSONB columns properly? Does `write_embeddings()` use `::vector` cast correctly?
- [ ] `scripts/collectors/nps_content_collector.py` — does `_make_request()` retry on 5xx but not 4xx? Does `collect_all_content()` write per-park for resumability?
- [ ] `scripts/collectors/nps_content_schemas.py` — does the HTML stripper handle edge cases (nested tags, entities)?
- [ ] `utils/embedding_client.py` — does the sync version match the async version's error handling?
- [ ] `api/queries.py` — does `fetch_semantic_search()` properly cast the embedding string with `::vector`?
- [ ] `api/nlq/parser.py` — does `_normalize_content_search_params()` gracefully drop unresolvable park codes (vs. raising)?
- [ ] `api/main.py` — does the `search_park_content` dispatch in `/query` pop `query` from params before passing remaining params?

### 10. Optional: run more parks

Once satisfied with the single-park test:

```bash
POSTGRES_HOST=localhost POSTGRES_PORT=5433 python scripts/collectors/nps_content_collector.py --write-db
POSTGRES_HOST=localhost POSTGRES_PORT=5433 python scripts/processors/embedding_indexer.py --force-refresh
```

Then try broader searches: `curl "http://localhost:8001/search?q=slot+canyons"`

---

## Original Plan Details

The sections below preserve the original plan specification for reference.

<details>
<summary>Step 1: Docker & Database Infrastructure</summary>

### 1a. Switch Docker image to support pgvector

**File:** `docker-compose.yml`

Change the `db` service from using `image:` directly to using a custom Dockerfile build, since we need both pgvector and PostGIS in the same image.

**New file:** `docker/Dockerfile.db`

Build from `pgvector/pgvector:pg16` and install PostGIS on top:

```dockerfile
FROM pgvector/pgvector:pg16
RUN apt-get update && apt-get install -y postgresql-16-postgis-3 && rm -rf /var/lib/apt/lists/*
```

Update `docker-compose.yml` `db` service to use `build:` instead of `image:`.

After this change, rebuild the database container:

```bash
docker compose down -v && docker compose up --build -d
```

### 1b. Add pgvector extension to init-db.sh

**File:** `docker/init-db.sh`

Add `CREATE EXTENSION IF NOT EXISTS vector;` alongside the existing `postgis` and `pg_trgm` extensions.

### 1c. Create SQL schema for content tables

**New file:** `sql/schema/nps_content.sql`

Three tables:

**`nps_thingstodo`** — raw content from `/thingstodo` endpoint:
- `id` (PK), `park_code` (FK to parks), `title`, `short_description`, `long_description`
- Structured fields: `activities` (JSONB), `topics` (JSONB), `tags` (JSONB), `season` (JSONB), `duration`
- Additional: `pets_description`, `fees_description`, `accessibility`, `location_description`, `url`, `latitude`, `longitude`, `collected_at`

**`nps_places`** — raw content from `/places` endpoint:
- `id` (PK), `park_code` (FK to parks), `title`, `short_description`, `body_text`, `audio_description`
- `tags` (JSONB), `url`, `latitude`, `longitude`, `collected_at`

**`content_embeddings`** — embedded text chunks for vector search:
- `id` (SERIAL PK), `park_code` (FK to parks), `source_type` (thingstodo/places/park_description), `source_id`, `title`
- `chunk_text` (the embedded text), `embedding` (vector(768)), `metadata` (JSONB), `collected_at`
- HNSW index on `embedding` column for efficient similarity search (good for small-medium datasets, no training data needed unlike IVFFlat)

Indexes: park_code on all three tables, source_type on embeddings, HNSW vector index.

Follow existing schema conventions: `CREATE TABLE IF NOT EXISTS`, constraints, `COMMENT ON` statements.

Add this file to `init-db.sh` schema loading loop, after `usgs_trail_elevations.sql`.

### 1d. Update DatabaseWriter

**File:** `scripts/database/db_writer.py`

- Add `nps_thingstodo`, `nps_places`, and `content_embeddings` to `table_dependencies` dict (all depend on `parks`)
- Add `write_thingstodo()`, `write_places()`, and `write_embeddings()` methods following the existing `write_parks()` upsert pattern
- For `write_embeddings()`: use raw SQL with `::vector` cast to write embedding vectors (e.g., `:embedding::vector`), consistent with how all other write methods use `text()` — no `pgvector` Python package needed
- Add `ensure_table_exists()` cases for the new tables
- Add table creation methods that execute SQL from the schema file

</details>

<details>
<summary>Step 2: NPS Content Collector</summary>

### 2a. Configuration

**File:** `config/settings.py`

Add to the `Config` class:

```python
# NPS Content Collection Settings
NPS_CONTENT_DEFAULT_OUTPUT_CSV: str = "artifacts/nps_content_collected.csv"
NPS_CONTENT_LOG_FILE: str = "logs/nps_content_collector.log"
NPS_CONTENT_THINGSTODO_ENDPOINT: str = "/thingstodo"
NPS_CONTENT_PLACES_ENDPOINT: str = "/places"
NPS_CONTENT_PAGE_SIZE: int = 50
NPS_CONTENT_MAX_RETRIES: int = 2
NPS_CONTENT_RETRY_DELAY: float = 3.0
```

### 2b. Logging

**File:** `utils/logging.py`

Add `setup_nps_content_collector_logging()` following the existing pattern (calls `setup_logging()` with `config.NPS_CONTENT_LOG_FILE` and logger name `"nps_content_collector"`).

### 2c. Pydantic schemas for API responses

**New file:** `scripts/collectors/nps_content_schemas.py`

Pydantic models for validating NPS API responses:

- `NPSThingsToDoResponse` — validates a single `/thingstodo` item. Key fields: `id`, `title`, `shortDescription`, `longDescription`, `tags`, `relatedParks`, `season`, `duration`, `petsDescription`, `arePetsPermitted`, `feeDescription`, `isReservationRequired`, `doFeesApply`, `accessibilityInformation`, `latitude`, `longitude`, `url`. Strip HTML from description fields during validation.
- `NPSPlaceResponse` — validates a single `/places` item. Key fields: `id`, `title`, `listingDescription`, `bodyText`, `audioDescription`, `tags`, `relatedParks`, `latitude`, `longitude`, `url`. Strip HTML from body text during validation.
- HTML stripping utility: use `html.parser` (stdlib) to strip HTML tags from description fields. Keep it simple — strip tags, don't preserve structure.

Follow existing `nps_schemas.py` patterns: `Field(...)`, `@field_validator`, `@model_validator(mode="after")`, coordinate validation.

### 2d. Collector script

**New file:** `scripts/collectors/nps_content_collector.py`

Class: `NPSContentCollector`

**Constructor** (follow `nps_collector.py` patterns):

```python
def __init__(
    self,
    api_key: str | None = None,
    log_level: str | None = None,
    write_db: bool = False,
    engine: Engine | None = None,
) -> None:
```

- Initialize `requests.Session` with NPS API headers (same `X-Api-Key` + `User-Agent` pattern as `nps_collector.py`)
- Set up logger via `setup_nps_content_collector_logging()`
- Conditionally create `DatabaseWriter` if `write_db=True`
- Track completed parks via `db_writer.get_completed_records()` for resumability

**Key methods:**

1. `fetch_thingstodo_for_park(park_code: str) -> list[dict]`
   - `GET /thingstodo?parkCode={park_code}&limit=50&start=0`
   - Paginate through all results (same `limit`/`start`/`total` pattern as existing collector)
   - Validate each item with `NPSThingsToDoResponse`
   - Return list of validated dicts

2. `fetch_places_for_park(park_code: str) -> list[dict]`
   - `GET /places?parkCode={park_code}&limit=50&start=0`
   - Same pagination/validation pattern
   - Return list of validated dicts

3. `get_park_codes_from_db() -> list[str]`
   - Query `SELECT park_code FROM parks ORDER BY park_code`
   - Ensures we only collect content for parks already in the database

4. `collect_all_content(test_limit: int | None = None, force_refresh: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]`
   - Get park codes from DB
   - Apply `test_limit` if set
   - Skip already-collected parks (unless `force_refresh`)
   - For each park: fetch thingstodo + places with rate limiting (`time.sleep`)
   - Log progress: `"Collected {n} thingstodo and {m} places for {park_code} ({i}/{total})"`
   - Return two DataFrames (thingstodo_df, places_df)

5. `save_results(thingstodo_df, places_df)` — save to CSV files in `artifacts/`

**Main function** with argparse (follow existing pattern):
- `--test-limit N` — process first N parks
- `--write-db` — write to database
- `--force-refresh` — reprocess all parks
- `--delay SECONDS` — delay between API calls
- `--log-level LEVEL` — logging verbosity

**Error handling:** Retry on 5xx, don't retry on 4xx, log all errors with context, use custom exceptions from `utils/exceptions.py`. Re-raise `NpsHikesError` exceptions.

### 2e. Orchestrator integration

**File:** `scripts/orchestrator.py`

Add new step after NPS Data Collection (step 1), before trail collectors:

```python
("NPS Content Collection", "scripts/collectors/nps_content_collector.py", True),
```

</details>

<details>
<summary>Step 3: Text Chunking & Embedding Pipeline</summary>

### 3a. Ollama embedding client

**New file:** `utils/embedding_client.py`

Thin wrapper around Ollama's `/api/embed` endpoint, placed in `utils/` because it's shared by both the API layer (`api/main.py`) and the pipeline layer (`scripts/processors/embedding_indexer.py`). This follows the same pattern as `utils/logging.py` and `utils/exceptions.py` — shared infrastructure that both `api/` and `scripts/` import from. Keeping it out of `api/nlq/` avoids creating a `scripts/ → api/` dependency that doesn't exist elsewhere.

- `async def get_embeddings(texts: list[str]) -> list[list[float]]` — async version for API use. Calls `POST {OLLAMA_BASE_URL}/api/embed` with `{"model": "nomic-embed-text", "input": texts}`. Supports batching (Ollama accepts a list).
- `def get_embeddings_sync(texts: list[str]) -> list[list[float]]` — synchronous version for collector scripts (which aren't async). Uses `httpx` sync client.
- Raises `LlmConnectionError` on Ollama connection failures (same as `api/nlq/ollama_client.py`).

Add `OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"` to `config/settings.py`.

### 3b. Text chunking logic

**New file:** `scripts/processors/text_chunker.py`

Converts raw content records into embeddable text chunks:

- `chunk_thingstodo(record: dict) -> list[dict]` — concatenate title + short_description + long_description into a single chunk. Most items are short enough for one chunk. Split on paragraph boundaries if over ~2000 chars. Return list of dicts with: `chunk_text`, `source_type`, `source_id`, `title`, `park_code`, `metadata` (tags, season, duration, activity_type).

- `chunk_places(record: dict) -> list[dict]` — combine title + short_description + body_text. Same splitting logic. `source_type = "places"`.

- `chunk_park_description(park_code, park_name, description) -> list[dict]` — park descriptions are short (1-3 sentences), always a single chunk. `source_type = "park_description"`.

Prefix each chunk with title and park name for embedding context. Keep chunking simple — no overlapping windows or token counting.

### 3c. Embedding indexer script

**New file:** `scripts/processors/embedding_indexer.py`

Class: `EmbeddingIndexer`

```python
def __init__(
    self,
    log_level: str | None = None,
    engine: Engine | None = None,
    batch_size: int = 50,
) -> None:
```

**Key methods:**

1. `load_content_from_db() -> list[dict]` — query `nps_thingstodo`, `nps_places`, and `parks` (descriptions)
2. `chunk_all_content(records) -> list[dict]` — apply chunking from `text_chunker.py`
3. `embed_chunks(chunks) -> list[dict]` — call `get_embeddings_sync()` in batches, attach vectors
4. `write_embeddings_to_db(chunks_with_vectors)` — write to `content_embeddings` via `DatabaseWriter`
5. `index_all(force_refresh=False)` — full pipeline: load → chunk → embed → write

**Main function** with argparse:
- `--force-refresh` — clear and rebuild all embeddings
- `--batch-size N` — embedding batch size (default 50)
- `--log-level LEVEL`

### 3d. Logging and config for indexer

**File:** `utils/logging.py` — add `setup_embedding_indexer_logging()`
**File:** `config/settings.py` — add `EMBEDDING_INDEXER_LOG_FILE`, `EMBEDDING_BATCH_SIZE`, `EMBEDDING_DIMENSION`

</details>

<details>
<summary>Step 4: API — Standalone Search Endpoint</summary>

### 4a. Search query function

**File:** `api/queries.py`

Add `fetch_semantic_search()`:

```python
def fetch_semantic_search(
    query_embedding: list[float],
    park_code: str | None = None,
    source_type: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
```

SQL query using pgvector's `<=>` cosine distance operator:

```sql
SELECT
    ce.chunk_text, ce.title, ce.park_code,
    p.full_name AS park_name, ce.source_type, ce.source_id,
    1 - (ce.embedding <=> :query_embedding::vector) AS similarity_score,
    ce.metadata
FROM content_embeddings ce
JOIN parks p ON ce.park_code = p.park_code
WHERE 1=1
```

Dynamic `WHERE` clauses for `park_code` and `source_type` filters (same pattern as `fetch_trails()`). Order by distance ascending, apply limit.

### 4b. Pydantic response models

**File:** `api/models.py`

Add `SearchResult` and `SearchResponse`:

```python
class SearchResult(BaseModel):
    chunk_text: str
    title: str | None
    park_code: str
    park_name: str | None
    source_type: str
    source_id: str | None
    similarity_score: float
    metadata: dict[str, Any] | None

class SearchResponse(BaseModel):
    query: str
    result_count: int
    results: list[SearchResult]
```

### 4c. Search endpoint

**File:** `api/main.py`

New `GET /search` endpoint:

```python
@app.get("/search", response_model=SearchResponse, tags=["Search"])
async def semantic_search(
    q: str = Query(..., min_length=3, max_length=500),
    park_code: str | None = Query(None),
    source_type: str | None = Query(None),
    limit: int = Query(10, ge=1, le=50),
) -> dict[str, Any]:
```

Flow: embed query text via `get_embeddings()` (from `utils/embedding_client`) → call `fetch_semantic_search()` → return response.

Error handling: Ollama unavailable → 503, database error → 503, empty embedding → 422.

</details>

<details>
<summary>Step 5: NLQ Integration</summary>

### 5a. Add search tool to NLQ tools

**File:** `api/nlq/prompt.py`

Add 5th tool `search_park_content` to `TOOLS` list:
- Parameters: `query` (required string), `park_code` (optional), `limit` (optional, 1-50)
- Description guides the LLM to use it for descriptive/thematic questions ("waterfalls", "winter activities", "kid-friendly")

Update `_SYSTEM_MESSAGE_TEMPLATE` with guidance on when to use semantic search vs. structured tools.

### 5b. Add parser support

**File:** `api/nlq/parser.py`

- Add `"search_park_content"` to `VALID_FUNCTIONS`
- Add `_normalize_content_search_params()`: validate query present, resolve park_code, clamp limit to 1-50

### 5c. Add dispatch in /query endpoint

**File:** `api/main.py`

In the `/query` dispatch block:

```python
elif function_name == "search_park_content":
    query_embedding = await get_embeddings([params["query"]])
    results = fetch_semantic_search(
        query_embedding=query_embedding[0],
        park_code=params.get("park_code"),
        limit=params.get("limit", 10),
    )
```

</details>

<details>
<summary>Step 6: Dependencies</summary>

### 6a. Python dependencies

No new Python dependencies required. Vector columns are written via raw SQL with `::vector` cast, so the `pgvector` Python package is not needed. All existing dependencies (`sqlalchemy`, `httpx`, `pydantic`, etc.) already cover the new code.

### 6b. Ollama model setup

Prerequisite (document in README or getting-started):

```bash
ollama pull nomic-embed-text
```

### 6c. Configuration additions summary

All new `config/settings.py` entries:

```python
# NPS Content Collection
NPS_CONTENT_DEFAULT_OUTPUT_CSV = "artifacts/nps_content_collected.csv"
NPS_CONTENT_LOG_FILE = "logs/nps_content_collector.log"
NPS_CONTENT_THINGSTODO_ENDPOINT = "/thingstodo"
NPS_CONTENT_PLACES_ENDPOINT = "/places"
NPS_CONTENT_PAGE_SIZE = 50
NPS_CONTENT_MAX_RETRIES = 2
NPS_CONTENT_RETRY_DELAY = 3.0

# Embedding
OLLAMA_EMBEDDING_MODEL = "nomic-embed-text"
EMBEDDING_INDEXER_LOG_FILE = "logs/embedding_indexer.log"
EMBEDDING_BATCH_SIZE = 50
EMBEDDING_DIMENSION = 768
```

</details>

<details>
<summary>Step 7: Tests</summary>

### 7a. Unit tests — content collector

**New file:** `tests/unit/test_nps_content_collector.py`

```
class TestNPSContentCollector:
    test init with/without API key
    test fetch_thingstodo_for_park with mocked HTTP response
    test fetch_places_for_park with mocked HTTP response
    test pagination (mock multiple pages)
    test API error handling (timeout, 404, 500)
    test rate limit header logging
    test HTML stripping in schema validation
    test empty responses (park with no thingstodo)
    test get_park_codes_from_db with mock engine
```

Mock pattern: `patch.object(collector.session, "get")` with realistic NPS response structures.

### 7b. Unit tests — content schemas

**New file:** `tests/unit/test_nps_content_schemas.py`

```
class TestNPSThingsToDoSchema:
    test valid response passes validation
    test missing required fields raises ValidationError
    test HTML stripping in description fields
    test coordinate validation (valid, invalid, missing)
    test empty tags/activities handled gracefully

class TestNPSPlaceSchema:
    (same patterns for places)
```

### 7c. Unit tests — text chunker

**New file:** `tests/unit/test_text_chunker.py`

```
class TestChunkThingsToDo:
    test short content produces single chunk
    test long content splits on paragraph boundaries
    test chunk includes title prefix for context
    test metadata extracted correctly (tags, season, etc.)
    test empty description produces chunk from title only

class TestChunkPlaces:
    (same patterns)

class TestChunkParkDescription:
    test normal description produces single chunk
    test empty description returns empty list
```

### 7d. Unit tests — embedding client

**New file:** `tests/unit/test_embedding_client.py`

```
class TestGetEmbeddings:
    test successful embedding call (mock httpx)
    test batch embedding (multiple texts)
    test Ollama connection error raises LlmConnectionError
    test timeout handling
    test empty input returns empty list

class TestGetEmbeddingsSync:
    (same tests for sync version)
```

### 7e. Unit tests — search query and endpoint

Not yet written. Add to existing test files or new `tests/unit/test_search.py`:

```
class TestFetchSemanticSearch:
    test basic search returns results (mock DB)
    test park_code filter applied
    test source_type filter applied
    test limit respected
    test empty results

class TestSearchEndpoint:
    test GET /search with valid query (mock embedding + DB)
    test missing query returns 422
    test park_code filter works
    test Ollama unavailable returns 503
```

### 7f. Unit tests — NLQ parser updates

Updated existing parser test file with 7 new tests.

### 7g. Integration tests

Not yet written. Add `tests/integration/test_nps_content_collector_db.py`:

```
pytestmark = pytest.mark.integration

class TestNPSContentCollectorDatabaseIntegration:
    test collecting thingstodo for a single park and writing to DB
    test collecting places for a single park and writing to DB
    test content_embeddings table receives data after indexing
    test foreign key constraint to parks table
    test upsert behavior (re-running doesn't duplicate)
```

### 7h. Test fixtures

**File:** `tests/conftest.py`

Added: `sample_thingstodo_api_response`, `sample_places_api_response`, `sample_embedding_vector` (768-dim float list), `content_collector` (NPSContentCollector with test API key).

</details>

<details>
<summary>Step 8: Orchestrator Update</summary>

**File:** `scripts/orchestrator.py`

Final step order:

```python
steps = [
    ("NPS Data Collection",     "scripts/collectors/nps_collector.py",           True),
    ("NPS Content Collection",  "scripts/collectors/nps_content_collector.py",   True),
    ("OSM Trails Collection",   "scripts/collectors/osm_hikes_collector.py",     True),
    ("TNM Trails Collection",   "scripts/collectors/tnm_hikes_collector.py",     True),
    ("GMaps Import",            "scripts/collectors/gmaps_hiking_importer.py",   False),
    ("Trail Matching",          "scripts/processors/trail_matcher.py",           False),
    ("Elevation Collection",    "scripts/collectors/usgs_elevation_collector.py", True),
    ("Content Embedding",       "scripts/processors/embedding_indexer.py",       False),
]
```

</details>

---

## Deferred: LLM Answer Generation & Streamlit UI

Two capabilities are explicitly **out of scope** for this plan but are natural follow-ups:

### LLM answer generation

This plan implements the **retrieval** part of RAG — the `/search` endpoint and NLQ tool return ranked text chunks. The full RAG pattern adds a **generation** step: feed the retrieved chunks into an LLM as context and have it synthesize a natural language answer (e.g., "Capitol Reef and Zion both offer slot canyon experiences...").

This is deferred because the retrieval infrastructure is the hard part. Adding generation later is a small incremental change:

1. **Build a RAG prompt** — a function that takes the top-N search results and assembles them into a context block for the LLM, combining `park_name`, `title`, and `chunk_text` from each result (these are already returned by `fetch_semantic_search()`).

2. **Call the LLM** — one additional `call_ollama()` invocation using plain completion (no tools). The existing `api/nlq/ollama_client.py` already supports this. The system prompt would instruct the model to answer based only on the provided context, cite which parks the information comes from, and say "I don't know" if the context doesn't contain an answer.

3. **Response model update** — the `/query` response would include a `generated_answer` field (string) alongside the existing `results` (the raw chunks). This preserves the ability to inspect what the LLM was working with.

4. **Dispatch change** — in `api/main.py`, the `search_park_content` branch currently returns the raw search results. It would additionally pass those results through the generation function and include the synthesized answer.

The scope is small — roughly one new function, one new Ollama call, and a response field addition. The hard part (embedding infrastructure, vector storage, similarity search) is already done.

### Streamlit UI

The current Streamlit search box is designed around structured queries that produce trail/park tables and map markers. Knowledge questions ("which parks have slot canyons?") produce prose answers — a fundamentally different interaction pattern. Designing how this surfaces in the app (separate Q&A section? adaptive rendering? chat widget?) deserves its own iteration once the backend is working and we can experiment with real queries through the FastAPI docs page.

### Deployment constraints

The `/search` endpoint works in the deployed API on Render — it only needs the database (with embeddings) and Ollama for embedding the query text. However, Ollama is not available on Render's free tier, so `/search` only works when the API is running locally with Ollama.

The `/query` NLQ endpoint has the same constraint — it requires Ollama both for the LLM tool-call step and for embedding the extracted search query. This is inherent to the local-LLM architecture: there is no free hosted alternative to Ollama that provides both chat completion and embedding. The NLQ and semantic search features are local-only by design.

What **is** demo-able without Ollama: all the structured endpoints (`/parks`, `/trails`, `/stats`, `/search` results if pre-computed) continue to work in the deployed API. The semantic search and NLQ features are usable through the local FastAPI docs (`/docs`) or the local Streamlit app.

# RAG Concepts — A Practical Explanation

This document explains how Retrieval-Augmented Generation (RAG) works, using the NPS Hikes project as a concrete example throughout. Each step maps to specific files in the codebase and commands you can run to see what happens.

## The problem RAG solves

The existing NLQ system can answer **structured questions**: "trails over 5 miles in Zion" translates to SQL filters on columns like `length_miles` and `park_code`. But it can't answer **"which parks have slot canyons?"** because "slot canyons" isn't a column in any table. That information is buried in free-text descriptions. RAG lets you search unstructured text using meaning rather than exact keywords.

## The two phases

RAG has two distinct phases: **indexing** (done once, ahead of time) and **retrieval** (done at query time). Think of it like building a library index vs. looking something up in that index.

---

## Phase 1: Indexing (offline, one-time)

### Step 1: Collect raw text

You gather text documents. In this project, that means NPS API content — things-to-do descriptions like:

> *"Hike the Narrows in Zion National Park. Wade through the Virgin River between towering slot canyon walls up to 2,000 feet high..."*

The project collected 6,771 content items across 62 parks, drawn from two NPS API endpoints (`/thingstodo` and `/places`), plus the park descriptions already in the `parks` table.

**Files involved:**

| File | Role |
|------|------|
| `scripts/collectors/nps_content_collector.py` | `NPSContentCollector` class — fetches from the NPS API with pagination, retry on 5xx errors, and per-park writes for resumability |
| `scripts/collectors/nps_content_schemas.py` | Pydantic models (`NPSThingsToDoResponse`, `NPSPlaceResponse`) that validate API responses and strip HTML from description fields |
| `config/settings.py` | API endpoints, page size, retry settings (`NPS_CONTENT_*` entries) |
| `sql/schema/nps_content.sql` | `CREATE TABLE` for `nps_thingstodo` and `nps_places` (plus `content_embeddings` — used later) |

**Run it yourself:**

```bash
# Collect content for 1 park (test mode)
POSTGRES_HOST=localhost POSTGRES_PORT=5433 python scripts/collectors/nps_content_collector.py --test-limit 1 --write-db --log-level DEBUG

# Collect content for all parks
POSTGRES_HOST=localhost POSTGRES_PORT=5433 python scripts/collectors/nps_content_collector.py --write-db
```

**Inspect the results:**

```bash
# How many items were collected?
docker compose exec db psql -U seanangiolillo -d nps_hikes_db -c \
  "SELECT 'thingstodo' AS type, count(*) FROM nps_thingstodo
   UNION ALL
   SELECT 'places', count(*) FROM nps_places;"

# Sample a few titles
docker compose exec db psql -U seanangiolillo -d nps_hikes_db -c \
  "SELECT park_code, title FROM nps_thingstodo LIMIT 5;"

# CSV artifacts are also saved
ls artifacts/nps_*_collected.csv
```

### Step 2: Chunk the text

Embedding models have input size limits, and shorter, focused passages retrieve better than long documents. So you split text into **chunks** — self-contained passages.

For this project, chunking is simple because most NPS content items are already short (a few paragraphs). The chunker concatenates title + description into one passage, and only splits if the text is unusually long. A chunk might look like:

> *"Hike the Narrows\n\nWade through the Virgin River between towering slot canyon walls up to 2,000 feet high. This challenging 9.4-mile hike requires water shoes and is best attempted June through September."*

The title is prepended so the embedding captures what the content is about. The park code and park name are stored as **separate columns** alongside the chunk, not baked into the text. This is more efficient — the embedding focuses on semantic content, while structured metadata (park, source type) stays queryable via SQL filters.

**Why chunk at all?** Two reasons:

1. **Precision.** If you embed an entire page of text as one vector, a query about "waterfalls" might match a page that mentions waterfalls in one sentence among ten other topics. A focused chunk about waterfalls specifically will match more strongly.

2. **Model limits.** Embedding models have a maximum input length (typically 512-8192 tokens depending on the model). Chunks need to fit within this window.

**Files involved:**

| File | Role |
|------|------|
| `scripts/processors/text_chunker.py` | Three functions: `chunk_thingstodo()`, `chunk_places()`, `chunk_park_description()` — each assembles text from DB fields. `_split_text()` splits on paragraph boundaries at ~2000 chars, with `_split_long_paragraph()` as a fallback that splits on sentence boundaries |

**How chunking works in detail:**

- `chunk_thingstodo(record)` — concatenates `title + short_description + long_description`. Extracts metadata (tags, season, duration, activities) into a separate dict attached to each chunk.
- `chunk_places(record)` — concatenates `title + short_description + body_text`. Extracts tags as metadata.
- `chunk_park_description(park_code, park_name, description)` — wraps the park description with the park name. Always a single chunk (descriptions are short).
- If any concatenated text exceeds 2000 characters, `_split_text()` splits on `\n\n` paragraph boundaries. If a single paragraph is still too long, `_split_long_paragraph()` splits on sentence endings (`. `, `! `, `? `).

The chunker is a pure function — no database, no Ollama, no side effects. It's called by the embedding indexer (step 3).

### Step 3: Embed the chunks

This is the core concept. An **embedding model** converts text into a fixed-size array of numbers — a **vector**. For `nomic-embed-text` (the model used in this project), that's 768 floating-point numbers per chunk.

```
"Hike the Narrows in Zion..."  →  [0.023, -0.112, 0.847, ..., 0.034]  (768 floats)
```

What makes this useful: the model is trained so that **texts with similar meaning produce similar vectors**. The vectors for "slot canyon hike" and "narrow gorge trail" will be close together in 768-dimensional space, even though they share few exact words. The vectors for "slot canyon hike" and "campground reservation policy" will be far apart.

You don't control or interpret individual numbers in the vector. You just trust that proximity in this vector space corresponds to semantic similarity. This is the entire foundation of RAG — it's what makes "search by meaning" possible.

Each chunk's text and its vector get stored together in the `content_embeddings` table. The `embedding vector(768)` column holds the vector. pgvector's HNSW index makes similarity lookups fast without scanning every row.

After indexing, the `content_embeddings` table looks like:

| title | chunk_text | park_code | embedding | source_type |
|---|---|---|---|---|
| "Hike the Narrows" | "Hike the Narrows\n\nWade through the Virgin River..." | zion | [0.023, -0.112, ...] | thingstodo |
| "Angels Landing" | "Angels Landing\n\nA strenuous trail with..." | zion | [0.041, 0.089, ...] | thingstodo |
| "Capitol Reef National Park" | "Capitol Reef National Park\n\nExplore narrow slot canyons..." | care | [-0.017, 0.203, ...] | park_description |

Note that `park_code` and `title` are separate columns — the chunk text contains the semantic content, while structured metadata is stored independently. At query time, the API joins `park_code` to the `parks` table to include the full `park_name` in results.

**Files involved:**

| File | Role |
|------|------|
| `scripts/processors/embedding_indexer.py` | `EmbeddingIndexer` class — orchestrates the full pipeline: load from DB → chunk via `text_chunker.py` → embed via `embedding_client.py` → write to `content_embeddings` via `db_writer.py`. Always truncates existing embeddings before re-indexing to prevent duplicates. |
| `utils/embedding_client.py` | Thin wrapper around Ollama's `/api/embed` endpoint. Two versions: `get_embeddings()` (async, used by the API) and `get_embeddings_sync()` (sync, used by the indexer script). Both raise `LlmConnectionError` on failures. |
| `scripts/database/db_writer.py` | `write_embeddings()` method — inserts chunks with `CAST(:embedding AS vector)` for pgvector compatibility |
| `sql/schema/nps_content.sql` | Defines `content_embeddings` table with `embedding vector(768)` column and HNSW index |
| `docker/Dockerfile.db` | Custom image: `pgvector/pgvector:pg16` base with PostGIS installed on top |

**Run it yourself:**

```bash
# Make sure the embedding model is available
ollama pull nomic-embed-text

# Run the indexer (truncates and rebuilds all embeddings)
POSTGRES_HOST=localhost POSTGRES_PORT=5433 python scripts/processors/embedding_indexer.py --log-level DEBUG

# Or run both collection + embedding via the orchestrator
POSTGRES_HOST=localhost POSTGRES_PORT=5433 python scripts/orchestrator.py --write-db --test-limit 1
```

**Inspect the results:**

```bash
# How many embeddings were created?
docker compose exec db psql -U seanangiolillo -d nps_hikes_db -c \
  "SELECT count(*) FROM content_embeddings;"

# Breakdown by source type
docker compose exec db psql -U seanangiolillo -d nps_hikes_db -c \
  "SELECT source_type, count(*) FROM content_embeddings GROUP BY source_type;"

# Sample some chunks with their text lengths
docker compose exec db psql -U seanangiolillo -d nps_hikes_db -c \
  "SELECT title, source_type, length(chunk_text) AS chars FROM content_embeddings LIMIT 10;"

# Verify the vector dimension
docker compose exec db psql -U seanangiolillo -d nps_hikes_db -c \
  "SELECT id, vector_dims(embedding) FROM content_embeddings LIMIT 1;"
```

---

## Phase 2: Retrieval (at query time)

### Step 4: Embed the query

A user asks: **"parks with slot canyons"**

That query text gets sent to the **same** embedding model:

```
"parks with slot canyons"  →  [0.019, -0.098, 0.831, ..., 0.041]
```

Because it's the same model, the query vector lives in the same 768-dimensional space as all the stored chunk vectors. This is essential — you can only compare vectors that were produced by the same model.

**Where this happens in code:** In `api/main.py`, the `/search` endpoint calls `await get_embeddings([q])` from `utils/embedding_client.py`. The same function is used in the `/query` NLQ dispatch when the LLM selects the `search_park_content` tool.

### Step 5: Find nearest vectors

pgvector computes the **cosine distance** between the query vector and every stored vector. (The HNSW index makes this efficient — it uses a graph structure to find approximate nearest neighbors without literally scanning every row.)

The closest matches come back:

| park_name | title | chunk_text | similarity |
|---|---|---|---|
| Capitol Reef National Park | Capitol Reef National Park | "Capitol Reef National Park\n\nExplore narrow slot canyons..." | 0.92 |
| Zion National Park | Hike the Narrows | "Hike the Narrows\n\nWade through towering slot canyon walls..." | 0.89 |
| Bryce Canyon National Park | Bryce Canyon National Park | "Bryce Canyon National Park\n\nWalk among hoodoos and narrow formations..." | 0.74 |

"Slot canyons" wasn't a keyword filter — the embedding model understood that "narrow slot canyon walls" and "slot canyons" are semantically close, even though the exact phrase doesn't appear. The `park_name` column comes from a JOIN to the `parks` table, not from the chunk text itself.

**Cosine similarity** measures the angle between two vectors, ranging from -1 (opposite) to 1 (identical). In practice, most text embeddings fall in the 0.3-0.95 range, where higher means more similar.

**Where this happens in code:** `api/queries.py` → `fetch_semantic_search()` executes a SQL query using pgvector's `<=>` cosine distance operator:

```sql
SELECT chunk_text, title, park_code, ...
       1 - (ce.embedding <=> CAST(:query_embedding AS vector)) AS similarity_score
FROM content_embeddings ce
ORDER BY ce.embedding <=> CAST(:query_embedding AS vector) ASC
LIMIT :limit
```

### Step 6: Return results

The `/search` endpoint returns these chunks as ranked search results. That's the **retrieval** part of RAG.

**Files involved:**

| File | Role |
|------|------|
| `api/main.py` | `GET /search` endpoint (standalone) and `POST /query` dispatch for `search_park_content` (NLQ integration) |
| `api/queries.py` | `fetch_semantic_search()` — builds and executes the pgvector similarity query with optional `park_code` and `source_type` filters |
| `api/models.py` | `SearchResult` and `SearchResponse` Pydantic models for the response shape |
| `api/nlq/prompt.py` | `search_park_content` tool definition that guides the LLM on when to use semantic search vs. structured queries |
| `api/nlq/parser.py` | `_normalize_content_search_params()` — validates the `query` param, resolves park codes, clamps limits |
| `utils/embedding_client.py` | `get_embeddings()` (async) — embeds the user's query text at request time |

**Try it yourself:**

```bash
# Start the API (if not already running via docker compose)
POSTGRES_HOST=localhost POSTGRES_PORT=5433 uvicorn api.main:app --port 8001 --reload

# Standalone semantic search
curl -s "http://localhost:8001/search?q=waterfalls" | python -m json.tool
curl -s "http://localhost:8001/search?q=slot+canyons&limit=5" | python -m json.tool
curl -s "http://localhost:8001/search?q=winter+activities&park_code=yose" | python -m json.tool

# NLQ integration (requires Ollama running with an LLM like qwen2.5)
curl -s -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{"query": "things to do in winter at Yosemite"}' | python -m json.tool

# Verify existing structured queries still work
curl -s -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{"query": "longest trails in Yosemite"}' | python -m json.tool

# Interactive docs (Swagger UI) — browse all endpoints including /search
open http://localhost:8001/docs
```

---

## The "generation" step (not in this plan, but worth understanding)

The full term is **Retrieval-Augmented Generation**. In a complete RAG system, the retrieved chunks get injected into an LLM prompt as context, and the LLM generates a natural language answer:

```
System: Answer the user's question based on the following context.

Context:
- [Capitol Reef National Park] Capitol Reef National Park: Explore narrow slot canyons...
- [Zion National Park] Hike the Narrows: Wade through towering slot canyon walls...

User: "Which parks have slot canyons?"

LLM: "Capitol Reef and Zion both offer slot canyon
      experiences. At Capitol Reef, you can explore..."
```

Notice how the context is assembled from separate fields (`park_name`, `title`, `chunk_text`) that are already available in the `/search` response. The retrieval step stores these as separate columns; the generation step would combine them into a prompt so the LLM knows which park each chunk belongs to.

This is the "augmented generation" part: the LLM's response is *augmented* by *retrieved* context. Without retrieval, the LLM would have to rely on whatever it memorized during training, which might be wrong or outdated. With retrieval, it gets fresh, specific facts from your own database.

This plan implements retrieval only. Adding generation later is straightforward — it's just one additional Ollama call using the chunks as prompt context, assembled from the fields already returned by `fetch_semantic_search()`. The retrieval infrastructure is the hard part.

---

## Why chunking and embedding are separate steps

The plan has these as distinct scripts (`text_chunker.py` and `embedding_indexer.py`). This separation matters:

- **Chunking** is pure text manipulation — no model, no Ollama, fast. You can iterate on your chunk strategy (what fields to include, how to split, what context to prepend) without re-embedding anything.

- **Embedding** requires the Ollama model and is slower (network calls, model inference). You only want to re-embed when chunks actually change.

If you later decide to include tags in the chunk text, or change the split threshold from 2000 to 1500 characters, you modify the chunker and re-run the indexer. The separation keeps the feedback loop fast for the part you'll iterate on most.

---

## Key vocabulary summary

| Term | What it means |
|------|---------------|
| **RAG** | Retrieval-Augmented Generation — search for relevant text, then optionally feed it to an LLM for answer synthesis |
| **Embedding** | Converting text into a fixed-size numeric vector that captures its meaning |
| **Embedding model** | A neural network trained to produce embeddings where similar texts have similar vectors (e.g., `nomic-embed-text`) |
| **Vector** | An array of floats (e.g., 768 numbers) representing a text's position in semantic space |
| **Chunk** | A self-contained passage of text, sized appropriately for embedding (typically a few hundred words) |
| **Vector database** | A database that can store vectors and efficiently find the nearest neighbors to a query vector (pgvector in this project) |
| **Cosine similarity** | A measure of how close two vectors are, from -1 (opposite) to 1 (identical) |
| **HNSW index** | Hierarchical Navigable Small World — a graph-based index structure that makes approximate nearest-neighbor search fast without scanning every vector |
| **Semantic search** | Searching by meaning rather than exact keyword matching — enabled by comparing embedding vectors |
| **Retrieval** | Finding the most relevant text chunks for a given query |
| **Generation** | Using an LLM to synthesize a natural language answer from retrieved context |

---

## The flow in this project

```
INDEXING (one-time):

  NPS API ─→ nps_content_collector.py ─→ nps_thingstodo / nps_places tables
    /thingstodo                              │
    /places                            text_chunker.py
                                       (split into passages, prepend title)
                                             │
                                       embedding_indexer.py
                                       (Ollama nomic-embed-text → 768-dim vectors)
                                             │
                                       content_embeddings table
                                       (text + vector, indexed by HNSW)


RETRIEVAL (per query):

  User: "slot canyons"
       │
       ▼
  api/main.py  ─→  GET /search  or  POST /query (NLQ)
       │
       ▼
  utils/embedding_client.py
  (embed query with same nomic-embed-text model)
       │
       ▼
  api/queries.py → fetch_semantic_search()
  (pgvector <=> cosine distance, ORDER BY similarity)
       │
       ▼
  Ranked text chunks returned as JSON
```

---

## All files at a glance

### New files

| File | Layer | Purpose |
|------|-------|---------|
| `docker/Dockerfile.db` | Infrastructure | Custom DB image: `pgvector/pgvector:pg16` + PostGIS |
| `sql/schema/nps_content.sql` | Infrastructure | Schema for all 3 new tables + HNSW index |
| `scripts/collectors/nps_content_collector.py` | Indexing | Fetches from NPS API with pagination, retry, resumability |
| `scripts/collectors/nps_content_schemas.py` | Indexing | Pydantic validation + HTML stripping for API responses |
| `scripts/processors/text_chunker.py` | Indexing | Paragraph/sentence splitting at ~2000 chars |
| `scripts/processors/embedding_indexer.py` | Indexing | Full pipeline: load → chunk → embed → write |
| `utils/embedding_client.py` | Shared | Ollama `/api/embed` wrapper (async + sync) |
| `tests/unit/test_nps_content_collector.py` | Tests | 10 collector tests |
| `tests/unit/test_nps_content_schemas.py` | Tests | 17 schema validation tests |
| `tests/unit/test_text_chunker.py` | Tests | 9 chunker tests |
| `tests/unit/test_embedding_client.py` | Tests | 10 embedding client tests |

### Modified files

| File | Layer | What changed |
|------|-------|-------------|
| `docker-compose.yml` | Infrastructure | `db` service uses `build:` instead of `image:` |
| `docker/init-db.sh` | Infrastructure | Added `vector` extension + `nps_content.sql` |
| `config/settings.py` | Config | 12 new settings for content collection + embedding |
| `utils/logging.py` | Shared | Two new logging setup functions |
| `scripts/database/db_writer.py` | Indexing | `write_thingstodo()`, `write_places()`, `write_embeddings()` |
| `scripts/orchestrator.py` | Indexing | Steps 2 and 8 added to pipeline |
| `api/main.py` | Retrieval | `GET /search` + `search_park_content` dispatch in `POST /query` |
| `api/models.py` | Retrieval | `SearchResult` + `SearchResponse` |
| `api/queries.py` | Retrieval | `fetch_semantic_search()` with pgvector `<=>` |
| `api/nlq/prompt.py` | Retrieval | 5th tool definition + system message guidance |
| `api/nlq/parser.py` | Retrieval | `search_park_content` validation + normalization |
| `tests/conftest.py` | Tests | 4 new fixtures |
| `tests/unit/test_nlq_prompt.py` | Tests | Updated assertions + 3 new tests |
| `tests/unit/test_nlq_parser.py` | Tests | 7 new normalization tests |

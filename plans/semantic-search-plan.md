# Semantic Trail Search Plan

## Context

The RAG pipeline (collection → chunking → embedding → vector search) is complete and working. See the file /plans/rag-plan.md for details. The `/search` endpoint returns ranked text chunks from NPS content. However, many of those chunks describe specific trails — `nps_thingstodo` has 365 records with "trail" in the title, and `nps_places` has 1,104. These contain rich semantic information about individual trails.

Currently, a query like "waterfall hikes in California" can only return raw text chunks via `search_park_content`. The goal is to bridge semantic search results back to structured trail data, so queries like this produce a filtered trail list visible on the map and in the data table — the same experience as a structured `search_trails` query.

**Approach**: Pre-compute a mapping between content titles and trail names during indexing (reusing the existing `SequenceMatcher` + preprocessing pattern from `trail_matcher.py`). At query time, semantic search results JOIN through this mapping to return full trail data. When no trail matches exist, fall back to a generated prose answer.

---

## How to use this plan

Work through steps in order. Each step requires **human verification** before proceeding to the next. Tests are written alongside the code they test — not deferred to the end.

---

## Step 1: Content-to-Trail Mapping Table + Linker Script — COMPLETE

**Goal**: Pre-compute which content chunks correspond to which trails.

**Status**: Implemented and verified. All code merged, linker run against production data.

### Files created

| File | Purpose |
|------|---------|
| `sql/schema/content_trail_mapping.sql` | Schema with FK to content_embeddings (CASCADE), CHECK on trail_source, indexes |
| `scripts/processors/content_trail_linker.py` | Fuzzy-matches content titles to trail names via SequenceMatcher + containment boost |
| `tests/unit/test_content_trail_linker.py` | 54 unit tests covering preprocessing, similarity, TNM priority, edge cases |

### Files modified

| File | Change |
|------|--------|
| `config/settings.py` | Added `CONTENT_TRAIL_LINKING_THRESHOLD` (0.5), `CONTENT_TRAIL_LINKING_LOG_FILE` |
| `utils/logging.py` | Added `setup_content_trail_linker_logging()`, fallback config value |
| `docker/init-db.sh` | Added `content_trail_mapping.sql` after `nps_content.sql` |
| `scripts/orchestrator.py` | Added "Content-Trail Linking" step after "Content Embedding" |
| `scripts/database/db_writer.py` | Added `content_trail_mapping` to dependencies, drop order, `ensure_table_exists` |

### Implementation notes

- `TRAIL_WORDS_TO_REMOVE` ordered longest-first to prevent partial replacements ("trailhead" before "trail")
- Queries use `sqlalchemy.text()` (aliased `sa_text`) to support `:param` binding and `::` casts with `pd.read_sql`
- Linker truncates-and-rebuilds on each run (same pattern as embedding_indexer)

### Production run results

```
Total embeddings processed: 10,403
Matched to TNM trails:       4,030
Matched to OSM trails:       1,401
No match found:               4,972
Match rate:                   52.2%
```

### Verification checklist

- [x] Run linker against existing 10,403 embeddings — 5,431 mappings generated
- [x] Match rate 52.2% — within expected 30-50%+ range
- [x] Inspect sample matches manually for quality (see queries below)
- [x] Check for false positives (generic activities incorrectly matched to trails)
- [x] Evaluate threshold: is 0.5 the right default? No, changed to 0.7
- [x] All 477 unit tests pass (423 existing + 54 new, zero regressions)
- [x] New linker unit tests pass (54/54)

### Verification queries

Run these against the Docker database (`-h localhost -p 5433 -U seanangiolillo -d nps_hikes_db`) to validate match quality.

#### 1. Unmatched content titles (what didn't match)

```sql
-- Unmatched embeddings — should be generic activities, not trail-specific content
SELECT ce.title, ce.park_code, ce.source_type
FROM content_embeddings ce
WHERE ce.source_type IN ('thingstodo', 'places')
  AND ce.title IS NOT NULL
  AND ce.title != ''
  AND ce.id NOT IN (SELECT content_embedding_id FROM content_trail_mapping)
ORDER BY ce.park_code, ce.title
LIMIT 50;
```

**What to look for**: Titles like "Attend a Ranger Program", "Go Stargazing", "Junior Ranger Program" are correctly unmatched. Titles like "Hike to Vernal Fall" or "Angels Landing Trail" being unmatched would indicate a problem.

#### 2. Matched content for a specific park (spot-check quality)

```sql
-- All content for one park, showing matched vs unmatched
SELECT
    ce.title,
    ctm.trail_name,
    ctm.trail_source,
    ROUND(ctm.match_confidence::numeric, 3) AS confidence
FROM content_embeddings ce
LEFT JOIN content_trail_mapping ctm ON ce.id = ctm.content_embedding_id
WHERE ce.park_code = 'yose'
  AND ce.source_type IN ('thingstodo', 'places')
  AND ce.title IS NOT NULL
ORDER BY ctm.match_confidence DESC NULLS LAST;
```

**What to look for**: Trail-specific titles should have matches with high confidence (>0.7). Generic activity titles should show NULL for trail_name.

#### 3. Confidence score distribution

```sql
-- How are match scores distributed? Are there many borderline matches?
SELECT
    CASE
        WHEN match_confidence >= 0.9 THEN '0.90-1.00 (excellent)'
        WHEN match_confidence >= 0.8 THEN '0.80-0.89 (strong)'
        WHEN match_confidence >= 0.7 THEN '0.70-0.79 (good)'
        WHEN match_confidence >= 0.6 THEN '0.60-0.69 (moderate)'
        WHEN match_confidence >= 0.5 THEN '0.50-0.59 (borderline)'
    END AS score_bucket,
    COUNT(*) AS count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) AS pct
FROM content_trail_mapping
GROUP BY score_bucket
ORDER BY score_bucket DESC;
```

**What to look for**: If most matches are in the 0.50-0.59 range, they may be low quality and the threshold should be raised. If very few are borderline, 0.5 is fine. Update: switched to 0.7.

#### 4. Borderline matches (evaluate threshold)

```sql
-- Look at the weakest matches — are they true positives or false positives?
SELECT
    content_title,
    trail_name,
    trail_source,
    park_code,
    ROUND(match_confidence::numeric, 3) AS confidence
FROM content_trail_mapping
WHERE match_confidence < 0.6
ORDER BY match_confidence ASC
LIMIT 30;
```

**What to look for**: If most of these are reasonable matches (e.g. "Emerald Pools" → "Emerald Pools Trail"), keep 0.5. If many are false positives (e.g. "Bird Watching" → "Bird Creek Trail"), raise to 0.6 or 0.65. Update: bumped to 0.7

#### 5. False positive check — suspicious matches

```sql
-- Content titles that are clearly NOT trail-specific but somehow matched
SELECT
    content_title,
    trail_name,
    trail_source,
    park_code,
    ROUND(match_confidence::numeric, 3) AS confidence
FROM content_trail_mapping
WHERE content_title ILIKE ANY(ARRAY[
    '%ranger%', '%junior%', '%camping%', '%fishing%',
    '%stargazing%', '%photography%', '%bird watching%',
    '%kayak%', '%canoe%', '%raft%', '%ski%', '%snowshoe%'
])
ORDER BY match_confidence ASC;
```

**What to look for**: These should ideally not appear in the mapping at all. If they do, inspect whether the matched trail name is a coincidental fuzzy match.

#### 6. Match counts by source

```sql
-- TNM vs OSM breakdown, and per-park distribution
SELECT trail_source, COUNT(*) AS mappings
FROM content_trail_mapping
GROUP BY trail_source;

-- Top 10 parks by match count
SELECT park_code, COUNT(*) AS mappings
FROM content_trail_mapping
GROUP BY park_code
ORDER BY mappings DESC
LIMIT 10;
```

#### 7. Duplicate trail matches (same trail matched by multiple content items)

```sql
-- Trails matched by multiple content embeddings — expected for popular trails
SELECT
    trail_name,
    trail_source,
    park_code,
    COUNT(*) AS content_matches,
    ROUND(AVG(match_confidence)::numeric, 3) AS avg_confidence
FROM content_trail_mapping
GROUP BY trail_name, trail_source, park_code
HAVING COUNT(*) > 1
ORDER BY content_matches DESC
LIMIT 20;
```

#### 8. Coverage: what fraction of actual trails have content matches?

```sql
-- How many TNM trails have at least one content match?
SELECT
    'TNM' AS source,
    COUNT(DISTINCT t.permanent_identifier) AS total_trails,
    COUNT(DISTINCT ctm.trail_id) AS matched_trails,
    ROUND(COUNT(DISTINCT ctm.trail_id) * 100.0 / NULLIF(COUNT(DISTINCT t.permanent_identifier), 0), 1) AS pct
FROM tnm_hikes t
LEFT JOIN content_trail_mapping ctm ON ctm.trail_id = t.permanent_identifier AND ctm.trail_source = 'TNM'
WHERE t.name IS NOT NULL

UNION ALL

-- How many OSM trails have at least one content match?
SELECT
    'OSM' AS source,
    COUNT(DISTINCT o.osm_id) AS total_trails,
    COUNT(DISTINCT ctm.trail_id) AS matched_trails,
    ROUND(COUNT(DISTINCT ctm.trail_id::bigint) * 100.0 / NULLIF(COUNT(DISTINCT o.osm_id), 0), 1) AS pct
FROM osm_hikes o
LEFT JOIN content_trail_mapping ctm ON ctm.trail_id = o.osm_id::text AND ctm.trail_source = 'OSM'
WHERE o.name IS NOT NULL;
```

### Threshold tuning decision — RESOLVED

**Decision**: Raised threshold from 0.5 to **0.7** (matching `trail_matcher.py`).

**Evidence from production data**:
- 26% of matches fell in the 0.50-0.59 (borderline) bucket — most were false positives
- 11% in the 0.60-0.69 (moderate) bucket — most were also bad matches
- Matches at 0.7+ were consistently correct

**Change made**: `config/settings.py` → `CONTENT_TRAIL_LINKING_THRESHOLD: float = 0.7`

**Action required**: Re-run the linker to rebuild mappings with the new threshold:
```bash
POSTGRES_HOST=localhost POSTGRES_PORT=5433 POSTGRES_USER=seanangiolillo python scripts/processors/content_trail_linker.py --write-db
```

Then re-run verification queries 3 and 6 to confirm the borderline/moderate buckets are gone and the match count/rate are acceptable.

---

## Step 2: Query Function — `fetch_topic_trails()` — COMPLETE

**Goal**: A new query function that does semantic search → JOIN through content_trail_mapping → return structured trail data.

**Status**: Implemented and verified. Function added, 29 unit tests pass, live-tested against production data.

### Files created

| File | Purpose |
|------|---------|
| `tests/unit/test_topic_trails_query.py` | 29 unit tests covering trail results, dedup, filters, fallback, context |

### Files modified

| File | Change |
|------|--------|
| `api/queries.py` | Added `fetch_topic_trails()` (lines 920-1161) |

### Implementation

Signature:
```python
def fetch_topic_trails(
    query_embedding: list[float],
    park_code: str | None = None,
    state: str | None = None,
    limit: int = 20,
    geojson: bool = True,
) -> dict[str, Any]:
```

SQL logic (single CTE chain):
1. CTE `semantic_hits`: vector similarity search on content_embeddings (top 50, with optional park_code/state filters)
2. CTE `mapped`: INNER JOIN to content_trail_mapping to find trail-linked hits
3. CTEs `tnm_data` / `osm_data`: JOIN to actual trail tables for full trail data
4. CTE `osm_unique`: TNM-preferred dedup via `pg_trgm` similarity > 0.7 (same pattern as `fetch_trails`)
5. Final SELECT with parks, gmaps_hiking_locations_matched, usgs_trail_elevations JOINs

Python-side processing:
- Deduplicates trails matched by multiple content chunks (keeps highest-similarity entry)
- Collects all content matches into `topic_context` (content_title + chunk_text preview per match)
- Applies `limit` to unique trails and filters topic_context to match
- Fallback query only runs when trail_count == 0

Returns:
```python
{
    "trail_count": int,
    "total_miles": float,
    "trails": [...],           # same shape as fetch_trails
    "topic_context": [...],    # content_title + chunk_text_preview per trail
    "fallback_chunks": [...],  # unmatched semantic results (for generation fallback)
}
```

### Tests (29 total)

- Basic trail results and shape validation (4 tests)
- GeoJSON inclusion/exclusion (3 tests)
- Multi-content deduplication (3 tests)
- Topic context collection (4 tests)
- Limit enforcement (3 tests)
- Empty results (1 test)
- Fallback chunk population (3 tests)
- Park code and state filters (4 tests)
- Return structure completeness (4 tests)

### Verification

- [x] Start API locally, test with direct function calls or known embeddings
- [x] Confirm trail data shape matches `fetch_trails()` output
- [x] Confirm fallback_chunks populated for non-trail content
- [x] All 591 tests pass (562 existing + 29 new, zero regressions)

---

## Step 3: Replace `search_park_content` with `search_by_topic` in NLQ — COMPLETE

**Goal**: Unified semantic tool that the LLM routes to for all thematic/descriptive queries.

**Status**: Implemented and verified. Tool definition, parser, response models, and tests all updated.

### Rationale for consolidating into one tool

- The LLM doesn't need to predict whether a query will match trails (that's determined by the pre-computed mapping)
- Fewer tools = more reliable LLM classification
- The dispatch decides output format deterministically based on match results
- "waterfall hikes in CA" and "winter activities at Yosemite" both go to the same tool; the dispatch figures out whether the answer is trails or prose

### Files modified

| File | Change |
|------|--------|
| `api/nlq/prompt.py` | Replaced `search_park_content` tool with `search_by_topic`; added `state` parameter; updated system message guidance |
| `api/nlq/parser.py` | Replaced `search_park_content` with `search_by_topic` in `VALID_FUNCTIONS`; renamed `_normalize_content_search_params` → `_normalize_topic_search_params`; added state normalization (same pattern as `_normalize_trail_params`) |
| `api/models.py` | Added `TopicTrailResult`, `TopicSearchResponse`, `TopicContentResponse` response models |
| `tests/unit/test_nlq_prompt.py` | Updated tool name assertions to `search_by_topic`; updated param set to include `state`; added `test_includes_topic_search_guidance` |
| `tests/unit/test_nlq_parser.py` | Renamed all `search_park_content` tests to `search_by_topic`; added 3 new tests: state name resolution, state code uppercasing, invalid state dropped |

### Implementation notes

- No backward compat alias for `search_park_content` — solo project, clean break is simpler
- State normalization reuses the same `_STATE_NAME_TO_CODE` dict and regex pattern as `_normalize_trail_params`
- `TopicTrailResult` mirrors the `Trail` model fields but adds `topic_context` (content context string explaining why the trail matched)
- `TopicContentResponse` includes `generated_answer` field (nullable) for Step 5's generation fallback

### Verification

- [x] Updated unit tests pass (510 total — 88 NLQ tests + 422 others, zero regressions)
- [x] Manual test: LLM routes "trails over 5 miles in Zion" to `search_trails` — works end-to-end
- [x] Manual test: LLM routes "parks I haven't visited" to `search_parks` — works end-to-end
- [x] Manual test: "waterfall hikes in CA" — returns empty result (expected: dispatch in `main.py:1152` still references `search_park_content`, so `search_by_topic` has no matching elif branch yet; will be wired in Step 4)

### Manual test queries run

```bash
# Test 1: topic query — routing correct, dispatch not yet wired (Step 4)
curl -s -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{"query": "waterfall hikes in California"}' | python -m json.tool
# Result: empty — expected, dispatch needs Step 4

# Test 2: structured trail query — works end-to-end
curl -s -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{"query": "trails over 5 miles in Zion"}' | python -m json.tool | grep function_called
# Result: "function_called": "search_trails"

# Test 3: park query — works end-to-end
curl -s -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{"query": "parks I haven'\''t visited"}' | python -m json.tool | grep function_called
# Result: "function_called": "search_parks"
```

---

## Step 4: Dispatch Logic in `/query` Endpoint — COMPLETE

**Goal**: Wire `search_by_topic` through `fetch_topic_trails()` and return structured results.

**Status**: Implemented and verified. Dispatch wired, trails path and content fallback path both execute correctly. Existing search_trails and search_parks routing unaffected.

### Files modified

| File | Change |
|------|--------|
| `api/main.py` | Added `fetch_topic_trails` import; replaced `search_park_content` dispatch branch with `search_by_topic` using `fetch_topic_trails()`, branching on `trail_count > 0` for trails vs content response |

### Implementation

Dispatch in `api/main.py` (lines ~1153-1183):

```python
elif function_name == "search_by_topic":
    query_text = params.pop("query")
    query_embedding = await get_embeddings([query_text])
    if not query_embedding or not query_embedding[0]:
        raise HTTPException(422, "Failed to generate embedding")

    topic_results = fetch_topic_trails(
        query_embedding=query_embedding[0],
        park_code=params.get("park_code"),
        state=params.get("state"),
        limit=params.get("limit", 20),
        geojson=True,
    )

    if topic_results["trail_count"] > 0:
        results = {
            "trail_count": topic_results["trail_count"],
            "total_miles": topic_results["total_miles"],
            "trails": topic_results["trails"],
            "topic_context": topic_results["topic_context"],
            "response_type": "trails",
        }
    else:
        fallback = topic_results.get("fallback_chunks", [])
        results = {
            "result_count": len(fallback),
            "results": fallback,
            "response_type": "content",
        }
```

### Verification

- [x] `"waterfall hikes in Yosemite"` → `search_by_topic`, returns trails with `response_type: "trails"`, topic_context populated with chunk text previews
- [x] `"ranger programs for kids"` → `search_by_topic`, content fallback branch executes (`response_type: "content"`, `result_count: 0`)
- [x] `"short hikes in Zion"` → `search_trails` (routing unchanged; zero results due to LLM over-filtering with `source: "OSM"` + `hiked: true`, not a dispatch issue)
- [x] `"parks I haven't visited"` → `search_parks` (routing unchanged, returns unvisited parks correctly)
- [x] `"best time to visit Grand Canyon"` → LLM routes to `search_parks` instead of `search_by_topic` (prompt-tuning issue, not a dispatch bug)
- [x] All 510 unit tests pass (zero regressions)

### Observation: content fallback is hard to trigger

In practice, the content fallback path (`trail_count == 0`) is difficult to reach because the content_trail_mapping covers 52% of embeddings at the 0.7 threshold. Most topic queries — even tangential ones like "wildlife viewing" or "winter activities" — find semantic hits that happen to be trail-mapped. When the fallback *does* trigger (e.g., "ranger programs for kids"), the fallback query itself often returns 0 chunks because after excluding trail-mapped content from the top 50 semantic hits, nothing remains.

This has implications for Step 5 (generation fallback): generating prose from `fallback_chunks` may rarely activate in practice, since most `search_by_topic` queries will return trails. The generation feature may be more useful as a supplement to trail results (generating a summary from `topic_context`) rather than a fallback for empty trail results. Worth reconsidering the Step 5 design before implementing.

---

## Step 5: Generation Fallback — COMPLETE

**Goal**: When no trails match, generate a prose answer from the retrieved chunks.

**Status**: Implemented and verified. Generation function works end-to-end with Ollama, gracefully degrades when Ollama is unavailable, and all tests pass.

### Files created

| File | Purpose |
|------|---------|
| `api/nlq/generator.py` | `generate_from_context()` — formats context chunks and calls Ollama for prose generation |
| `tests/unit/test_nlq_generator.py` | 13 unit tests covering context formatting, generation, and error handling |

### Files modified

| File | Change |
|------|--------|
| `api/nlq/ollama_client.py` | Added `generate_completion()` — plain chat completion (no tools) for prose generation |
| `api/main.py` | Added `generate_from_context` import; updated `search_by_topic` fallback branch to call generation |

### Implementation

**`api/nlq/ollama_client.py`** — new function:
```python
async def generate_completion(messages: list[dict[str, str]]) -> str:
```
Same HTTP pattern as `call_ollama()` but omits the `tools` parameter. Returns the response text directly.

**`api/nlq/generator.py`** — new module:
```python
async def generate_from_context(
    user_query: str,
    context_chunks: list[dict],
) -> str | None:
```
- Formats chunks into labeled context block (`[1] Park Name - Title\ntext`)
- System prompt instructs model to answer from context only, cite parks, stay concise
- Returns `None` if chunks are empty, Ollama is unavailable, or response is empty
- Catches `LlmConnectionError` for graceful degradation (logs warning, returns None)

**`api/main.py`** dispatch change (lines ~1179-1192):
```python
else:
    fallback = topic_results.get("fallback_chunks", [])
    generated_answer = None
    if fallback:
        generated_answer = await generate_from_context(
            user_query=query_text,
            context_chunks=fallback,
        )
    results = {
        "result_count": len(fallback),
        "results": fallback,
        "response_type": "generated" if generated_answer else "content",
        "generated_answer": generated_answer,
    }
```

### Tests (13 total)

**TestFormatContext** (6 tests):
- Formats with park name and title
- Includes chunk text
- Empty chunks returns empty string
- Falls back to park_code when no park_name
- Falls back to "Untitled" when no title
- Chunks separated by blank lines

**TestGenerateFromContext** (7 tests):
- Returns generated answer (mocked Ollama)
- Returns None on empty chunks
- Returns None on Ollama unavailable (graceful degradation)
- Returns None on empty response
- Returns None on whitespace-only response
- Passes system prompt and formatted context to Ollama
- Context includes all chunks

### Verification

- [x] Direct function call with real Ollama → "There are Junior Ranger programs available for kids at both Yosemite National Park (ages 5-12, complete an activity booklet) and Grand Canyon National Park..."
- [x] With Ollama unavailable → returns None, logs warning, no crash
- [x] `"waterfall hikes in Yosemite"` → `search_by_topic`, trails returned (20 trails, 78.61 miles), topic_context populated — trail path unaffected
- [x] `"trails over 10 miles in Zion"` → `search_trails` — routing unchanged
- [x] `"parks I haven't visited"` → `search_parks` — routing unchanged
- [x] All 523 unit tests pass (510 existing + 13 new, zero regressions)

### Observation: fallback path rarely triggers (confirmed)

The Step 4 observation was correct — and more so than originally stated. With the 0.7 threshold, the actual mapping rate is **32.4%** (not 52.2%, which was at 0.5). However, even at 32.4% overall, the top 50 semantic hits for *any* query almost always include some trail-mapped content. Tested queries:

| Query | Routed to | Result |
|-------|-----------|--------|
| "ranger programs for kids" | search_by_topic | 6 trails (trail path) |
| "stargazing programs" | search_by_topic | 20 trails (trail path) |
| "bird watching opportunities" | search_by_topic | 6 trails (trail path) |
| "photography workshops at Pinnacles" | search_by_topic | 12 trails (trail path) |
| "history of the park service" | search_park_summary | LLM routes elsewhere |

The fallback path would only trigger for queries so narrow that zero trail-mapped content appears in the top 50 semantic hits. In practice, this is extremely rare because:
1. The LLM routes most non-trail queries to other tools (search_parks, search_park_summary, search_stats)
2. For queries that DO reach search_by_topic, the semantic search almost always finds some trail-mapped content among the top 50 hits

The generation code is correct and tested, but it will mainly be useful if the design changes in the future to generate summaries from `topic_context` (when trails ARE found) rather than only from `fallback_chunks` (when no trails found). This is a potential enhancement for Step 6 (Streamlit UI).

---

## Step 6: Update `/search` Endpoint with `resolve_trails` — COMPLETE

**Goal**: Allow the standalone REST endpoint to also return matched trails, bridging semantic search to structured trail data without going through the NLQ pipeline.

**Status**: Implemented and verified. New params added, branching logic works, 4 new tests pass, manual curl tests confirmed.

### Rationale

The `/search` endpoint currently only returns raw semantic chunks. Adding `resolve_trails=true` lets REST API consumers get structured trail data from a semantic query. This is a self-contained API change — smaller than the Streamlit UI work — so it ships first.

### Files modified

| File                | Change                                                                                                                                                               |
|---------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `api/main.py`       | Added `resolve_trails` and `state` params to `/search`; added branching logic; changed `response_model` to `None` (`fetch_topic_trails` import already from Step 4)  |
| `tests/test_api.py` | Added `TestSearchEndpointResolveTrails` class with 4 tests                                                                                                           |

### Implementation

Add two new query parameters to `semantic_search()`:

```python
resolve_trails: bool = Query(
    default=False,
    description="When true, resolve semantic matches to structured trail data via content-trail mapping",
),
state: str | None = Query(
    default=None,
    description="Filter by 2-letter state code (e.g., 'CA'). Only used when resolve_trails=true",
    min_length=2,
    max_length=2,
    pattern="^[A-Z]{2}$",
),
```

Branching logic inside the try block:

```python
if resolve_trails:
    topic_results = fetch_topic_trails(
        query_embedding=query_embedding[0],
        park_code=park_code,
        state=state,
        limit=limit,
        geojson=False,
    )
    if topic_results["trail_count"] > 0:
        return {
            "query": q,
            "response_type": "trails",
            "trail_count": topic_results["trail_count"],
            "total_miles": topic_results["total_miles"],
            "trails": topic_results["trails"],
            "topic_context": topic_results["topic_context"],
        }
    else:
        fallback = topic_results.get("fallback_chunks", [])
        return {
            "query": q,
            "response_type": "content",
            "result_count": len(fallback),
            "results": fallback,
        }
else:
    # Original behavior unchanged
    results = fetch_semantic_search(...)
    return {"query": q, **results}
```

### Design decisions

- `response_model=None` — response shape varies by mode; keeps it simple
- `geojson=False` — `/search` is lightweight; use `/query` or `/trails` for geometry
- No generation — `/search` stays retrieval-only; generation lives in `/query`
- `source_type` silently ignored when `resolve_trails=True` (fetch_topic_trails doesn't accept it)

### Tests

New tests for the `/search` endpoint with `resolve_trails`:
- `test_resolve_trails_returns_trail_data` — verify `response_type: "trails"` with trail data
- `test_resolve_trails_fallback_to_content` — no trail matches, verify `response_type: "content"`
- `test_resolve_trails_false_default` — existing behavior unchanged
- `test_resolve_trails_with_state_param` — verify state param accepted

### Verification

- [x] `curl "localhost:8001/search?q=waterfalls&resolve_trails=true"` returns `{response_type: "trails", trail_count: 9, ...}`
- [x] `curl "localhost:8001/search?q=waterfalls"` still returns raw chunks `{result_count, results: [...]}`
- [x] `curl "localhost:8001/search?q=slot+canyons&resolve_trails=true&state=UT"` filters by state
- [x] `/docs` page renders correctly with new parameters documented
- [x] All 612 unit tests pass (608 existing + 4 new, zero regressions)

---

## Step 7: Always-Generate in `/query` Dispatch — COMPLETE

**Goal**: Call `generate_from_context()` on the trails path too (not only the fallback path), using `topic_context` as generation input. This makes the RAG pipeline complete — every `search_by_topic` query that returns trails also produces a generated prose summary.

**Status**: Implemented and verified. Always-generate wired, topic_context enriched, all tests pass.

### Rationale

Steps 4 and 5 revealed that the generation fallback (`trail_count == 0`) almost never fires. The content-trail mapping is comprehensive enough that nearly every semantic query finds trail-mapped content. Queries like "ranger programs for kids" still return 6 trails via the trail path. The generation code is correct and tested, but effectively dead code.

To showcase a true Retrieval-Augmented Generation pipeline, generation should **always** run when trails are found, producing a prose summary from the matched content alongside the structured trail data. This is a small dispatch change — the generator and `_format_context()` already exist.

### Shape mismatch to resolve

`topic_context` items (from `fetch_topic_trails`):
- `trail_id`, `trail_name`, `content_title`, `chunk_text_preview` (200 chars)

`_format_context()` in `generator.py` expects:
- `park_name` (or `park_code`), `title`, `chunk_text` (full text)

**Solution**: Enrich `topic_context` in `fetch_topic_trails()` with the missing fields (already available on the SQL row), then transform at the call site for generation.

### Files modified

| File | Change |
|------|--------|
| `api/queries.py` | Add `park_code`, `park_name`, `chunk_text` to topic_context items in `fetch_topic_trails()` |
| `api/main.py` | Update `search_by_topic` trails branch: transform topic_context → generation chunks, call `generate_from_context`, add `generated_answer` to response |
| `api/models.py` | Add `generated_answer: str \| None` to `TopicSearchResponse` |
| `tests/unit/test_topic_trails_query.py` | Update topic_context assertions for new fields |
| `tests/unit/test_nlq_generator.py` | Test `_format_context` with topic-context-shaped input |

### Implementation

**`api/queries.py`** — Enrich topic_context (~line 1066):

```python
topic_context.append({
    "trail_id": row.trail_id,
    "trail_name": row.trail_name,
    "content_title": row.content_title,
    "chunk_text_preview": (row.chunk_text[:200] if row.chunk_text else None),
    "park_code": row.park_code,       # NEW
    "park_name": row.park_name,       # NEW
    "chunk_text": row.chunk_text,     # NEW (full text for generation)
})
```

The SQL final SELECT already has `r.park_code`, `p.park_name`, and `r.chunk_text` on the row — no SQL changes needed.

**`api/main.py`** — Always-generate in trails branch (~line 1171):

```python
if topic_results["trail_count"] > 0:
    # Transform topic_context into the shape _format_context() expects
    generation_chunks = [
        {
            "park_name": ctx.get("park_name") or ctx.get("park_code", ""),
            "title": ctx.get("content_title", ""),
            "chunk_text": ctx.get("chunk_text", ""),
        }
        for ctx in topic_results["topic_context"]
        if ctx.get("chunk_text")
    ]
    generated_answer = None
    if generation_chunks:
        generated_answer = await generate_from_context(
            user_query=query_text, context_chunks=generation_chunks,
        )
    results = {
        "trail_count": topic_results["trail_count"],
        "total_miles": topic_results["total_miles"],
        "trails": topic_results["trails"],
        "topic_context": topic_results["topic_context"],
        "response_type": "trails",
        "generated_answer": generated_answer,
    }
```

The `else` branch (fallback, `trail_count == 0`) stays unchanged.

**Key design choice**: Transform data at the call site rather than modifying `_format_context()`. Keeps the generator generic and backward-compatible with the existing fallback path.

### Tests

**`tests/unit/test_topic_trails_query.py`**:
- Update existing topic_context assertions to verify `park_code`, `park_name`, `chunk_text`
- Add `test_topic_context_includes_park_and_full_text`

**`tests/unit/test_nlq_generator.py`**:
- Add `test_formats_topic_context_shaped_chunks` — verify `_format_context` with transformed input

### Verification

- [x] `"waterfall hikes in Yosemite"` → `search_by_topic` with `response_type: "trails"` AND `generated_answer` populated
- [x] With Ollama stopped → `generated_answer: null`, trails still returned (graceful degradation)
- [x] `"trails over 10 miles in Zion"` → `search_trails` — routing unchanged
- [x] All 525 unit tests pass (523 existing + 2 new, zero regressions)

---

## Step 8: Hybrid Search - Add Structured Filters to `search_by_topic`

**Goal**: Enable `search_by_topic` to accept structured filters (`hiked`, `min_length`, `max_length`, `source`) alongside semantic queries, allowing combined queries like "slot canyons I hiked" or "waterfall hikes over 5 miles in California".

**Status**: Complete.

**See**: [/plans/hybrid-search-implementation-plan.md](./hybrid-search-implementation-plan.md) for full implementation details.

**Summary**: Extend the `search_by_topic` tool definition and `fetch_topic_trails()` to accept the same filter parameters as `fetch_trails()`, applying them in SQL after semantic matching. This solves the problem where queries combining semantic terms with structured filters (e.g., "slot canyons i hiked out west") currently can't apply both dimensions.

**Key changes**:
- Add filter parameters to `search_by_topic` tool in `api/nlq/prompt.py`
- Extend `fetch_topic_trails()` signature in `api/queries.py`
- Apply filters in SQL WHERE clause after semantic matching and deduplication
- Update `/search` endpoint to accept filter parameters when `resolve_trails=true`
- Update LLM system prompt: tool selection now based on presence of semantic component

**Tool selection rule**: Use `search_by_topic` for queries with ANY semantic/descriptive component (even with filters). Use `search_trails` only for purely structured queries with no semantic component.

**Verification**: Completed. Hybrid queries now support semantic intent plus structured filters across both `/query` and `/search?resolve_trails=true`.

---

## Step 9: Streamlit UI Handling

**Goal**: Display `search_by_topic` results (including hybrid search with filters) in the Streamlit app — trails on map/table, generated summary in a card above the map, topic context in an expander, applied filters shown as chips.

**Status**: Complete.

### Challenge: trail data injection

The normal Streamlit flow calls `fetch_trails()` per park with sidebar filter params. But `search_by_topic` returns semantically-matched trails directly in the `/query` response — a pre-curated subset, not all trails for those parks. Setting sidebar filters alone would fetch ALL trails for the matched parks, losing the semantic relevance.

**Solution**: Store topic trail results in session state and inject them into `park_data`, bypassing the normal `fetch_trails()` call. Park boundaries and hiked points are still fetched normally.

### Trail data flow

```text
Normal:     sidebar filters → fetch_trails() per park → park_data → map/table
Topic:      /query response → session state → inject into park_data → map/table
Divergence: user changes filter → should_use_topic_results() → False → normal flow resumes
```

### Files modified

| File | Change |
|------|--------|
| `streamlit_app/components/nlq.py` | Add topic session state key, `_apply_topic_search_params`, topic chip, divergence check, `_render_topic_results_card`, public helpers |
| `streamlit_app/app.py` | Import new helpers, inject topic trails into `park_data` |

### Implementation

**`streamlit_app/components/nlq.py`**:

1. **New session state key**: `_TOPIC_TRAILS_KEY = "nlq_topic_trail_results"`. Add to `initialize_nlq_state()` and `_clear_nlq_state()`.

2. **New public helpers** (for `app.py` to use without importing private state):
   ```python
   def get_topic_trail_results() -> dict | None:
       """Return stored topic trail data, or None."""
       return st.session_state.get(_TOPIC_TRAILS_KEY)

   def should_use_topic_results() -> bool:
       """True if topic results are active and filters haven't diverged."""
       results = st.session_state.get(_TOPIC_TRAILS_KEY)
       if not results or not results.get("trails"):
           return False
       fn = st.session_state.get(_LAST_FUNCTION_KEY)
       if fn != "search_by_topic":
           return False
       params = st.session_state.get(_LAST_PARAMS_KEY) or {}
       return not _nlq_params_diverged(fn, params)
   ```

3. **`_apply_params_to_widgets`** — New `search_by_topic` branch:
   - Read full response from `_LAST_RESPONSE_KEY`
   - Store `results` in `_TOPIC_TRAILS_KEY`
   - Extract unique park_codes from trail results → set `park_multiselect`
   - Set state filter if provided
   - Reset hiked/length/source to show-all defaults (topic results are pre-curated)

4. **`_build_chip_texts`** — For `search_by_topic`, prepend `"Topic: {query}"` chip. Existing park/state chips render if those params are present.

5. **`_nlq_params_diverged`** — For `search_by_topic`, check park selection matches the topic results' park codes, and state filter matches if provided.

6. **`render_nlq_chips_and_results`** — After existing `search_stats` card block, add:
   ```python
   if function_called == "search_by_topic":
       _render_topic_results_card()
   ```

7. **`_render_topic_results_card()`** — New function:
   - If `generated_answer` exists: render in `st.container(border=True)` with header "Topic Summary"
   - If `topic_context` exists: render in `st.expander("Why these trails matched")` showing trail name, content title, chunk preview per match

**`streamlit_app/app.py`**:

1. Import `get_topic_trail_results` and `should_use_topic_results` from `nlq.py`.

2. After the `park_data` fetch loop (after client-side trail name filter), inject topic trails:
   ```python
   if should_use_topic_results():
       topic_results = get_topic_trail_results()
       # Group topic trails by park_code
       topic_trails_by_park: dict[str, list[dict]] = {}
       for trail in topic_results["trails"]:
           pc = trail.get("park_code")
           if pc:
               topic_trails_by_park.setdefault(pc, []).append(trail)

       for pc, trails in topic_trails_by_park.items():
           total_miles = sum(t.get("length_miles", 0) for t in trails)
           park_data.setdefault(pc, {"boundary": None, "hiked_points": None, "trails": None})
           park_data[pc]["trails"] = {
               "trail_count": len(trails),
               "total_miles": round(total_miles, 2),
               "trails": trails,
               "pagination": {"limit": len(trails), "offset": 0,
                              "total_count": len(trails), "has_next": False, "has_prev": False},
           }
   ```

### Tests

No existing Streamlit component tests in the codebase. If tests are added, they should cover:
- `_apply_params_to_widgets` with `search_by_topic` + trails response
- `_apply_params_to_widgets` with `search_by_topic` + content response
- Chip rendering for topic queries
- `should_use_topic_results` under various state conditions

### Verification

- [x] Run Streamlit, enter "waterfall hikes in California" → trails appear on map + table, generated summary card above map, topic context in expander
- [x] Enter "short trails in Zion" → works via `search_trails` (existing flow unchanged)
- [x] Enter "parks I haven't visited" → works via `search_parks` (unchanged)
- [x] After a topic search, change a sidebar filter → topic results clear, normal filtering resumes
- [x] With Ollama stopped → trails still show, summary card doesn't appear (graceful degradation)
- [x] Click map markers, use sidebar filters — still functional

See [/plans/streamlit-hybrid-ux-update.md](./streamlit-hybrid-ux-update.md) for the implementation notes and final UX decisions.

---

## Step 10: API Tutorial + Documentation

**Goal**: Document semantic search and hybrid search features in API tutorial.

**Status**: Complete.

**Files modified**:
- `docs/api-tutorial.md`
- `README.md`
- `streamlit_app/README.md`
- `docs/index.md`

Documentation now covers:
- the `/search` endpoint for raw semantic retrieval
- hybrid search via `/search?resolve_trails=true`
- topic-based and hybrid NLQ examples via `/query`
- how semantic search differs from purely structured `/trails` queries
- the Streamlit app's topic-result behavior, chips, and generated summary handling

The API tutorial root-endpoint example was also updated to include `/search`.

### Verification

- [ ] Docs build cleanly (if using mkdocs or similar)
- [ ] Examples in tutorial work when copy-pasted

---

## Future Enhancements

### Regional Query Support

**Goal**: Map regional terms ("out west", "southwest", "Pacific Northwest") to multiple state filters.

**Status**: Deferred - separate task independent of hybrid search implementation.

**Context**: Currently, `state` parameter accepts a single 2-letter code. Queries like "slot canyons out west" should ideally map to multiple western states (`["UT", "AZ", "CO", "NV", "NM", "WY", "MT", "ID"]`).

**Approach**:
1. Change `state: str | None` to `states: list[str] | None` in `fetch_topic_trails()` and `fetch_trails()`
2. Update SQL to handle multiple states with OR conditions
3. Create regional mapping in prompt or parser:
   ```python
   REGIONS = {
       "out west": ["UT", "AZ", "CO", "NV", "NM", "WY", "MT", "ID"],
       "southwest": ["AZ", "NM", "UT", "NV"],
       "pacific northwest": ["WA", "OR"],
       "northeast": ["ME", "NH", "VT", "MA", "RI", "CT", "NY", "PA", "NJ"],
   }
   ```
4. Update LLM system prompt to recognize regional terms
5. Update parser to resolve regional terms to state lists
6. Update Streamlit UI to display regional/multi-state chips

**Rationale for deferring**: Orthogonal to hybrid search (semantic + filters). Regional mapping is a distinct NLQ enhancement that can be added later without breaking changes. Users can still specify single states in the interim.

**Return to this after hybrid search is fully extended to multi-state/regional interpretation.**

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Pre-computed vs query-time matching | Pre-computed | Reuses Python preprocessing, runs once, keeps query SQL simple |
| Matching storage | Separate `content_trail_mapping` table | Clean separation, rebuild independently, CASCADE on delete |
| Matching threshold | 0.7 (same as trail_matcher) | Initially tried 0.5 but 26% borderline + 11% moderate matches were mostly false positives; raised to 0.7 after manual review |
| Tool consolidation | Replace `search_park_content` → `search_by_topic` | LLM doesn't predict output format; dispatch decides deterministically |
| Output format decision | Dispatch-level (trail_count > 0?) | Simpler than LLM-level; always tries trail matching first |
| Generation: always vs fallback-only | Always-generate (Step 7) | Fallback path almost never fires; always-generate showcases full RAG pipeline |
| Generation: transform vs modify generator | Transform at call site | Keeps `_format_context()` generic; topic_context keys differ from fallback_chunks |
| `/search` endpoint: generation | No (retrieval-only) | Keeps `/search` fast and focused; generation lives in `/query` |
| `/search` endpoint: geometry | No (`geojson=False`) | `/search` is lightweight; use `/query` or `/trails` for geometry |
| Streamlit trail injection | Override `park_data` vs sidebar-only | Sidebar-only would fetch ALL trails for matched parks, losing semantic relevance |
| Streamlit divergence | Clear topic results on any filter change | Simple and predictable; user can escape topic search by adjusting any filter |
| **Hybrid search: where to apply filters** | SQL WHERE clause after semantic matching | Efficient, preserves similarity ranking, clean separation |
| **Hybrid search: filter parameters** | Same as `fetch_trails()` | Consistency, reuses existing validation |
| **Hybrid search: tool selection** | Semantic component present → `search_by_topic` | Simple rule, LLM extracts both dimensions |
| **Hybrid search: generation on filtered results** | Always generate when semantic matches exist | Provides context even when filters eliminate all trails |
| **Hybrid search: `/search` endpoint** | Add filter parameters | Enables hybrid search for REST API consumers |
| **Regional support (multi-state)** | Defer to separate task | Orthogonal concern, can be added later |

---

## Key Files Reference

| Purpose | File |
|---------|------|
| Trail matcher (pattern to follow) | `scripts/processors/trail_matcher.py:90-152` |
| Content-trail linker (Step 1) | `scripts/processors/content_trail_linker.py` |
| Content-trail mapping schema | `sql/schema/content_trail_mapping.sql` |
| Linker unit tests | `tests/unit/test_content_trail_linker.py` |
| Existing semantic search | `api/queries.py:783-858` |
| Topic trails query (Step 2) | `api/queries.py:920-1161` |
| Trail query (shape to match) | `api/queries.py:200-300` |
| `/search` endpoint (Step 6) | `api/main.py:985-1075` |
| NLQ dispatch (Steps 4, 5, 7) | `api/main.py:1078-1206` |
| NLQ tool definitions | `api/nlq/prompt.py:10-194` |
| NLQ parser | `api/nlq/parser.py` |
| Ollama client | `api/nlq/ollama_client.py` |
| Generator (Step 5, 7) | `api/nlq/generator.py` |
| Response models | `api/models.py` (TopicSearchResponse, TopicContentResponse) |
| Streamlit NLQ component (Step 8) | `streamlit_app/components/nlq.py` |
| Streamlit app main (Step 8) | `streamlit_app/app.py` |
| Topic trails tests | `tests/unit/test_topic_trails_query.py` |
| Generator tests | `tests/unit/test_nlq_generator.py` |
| Content embeddings schema | `sql/schema/nps_content.sql:69-101` |
| Config settings | `config/settings.py` |

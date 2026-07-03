# Trail Type Removal Plan

## Goal

Remove `trail_type` as a meaningful concept from the project, starting with the lowest-risk runtime changes and ending with schema cleanup.

This plan is intentionally implementation-oriented. It captures the architecture and debugging findings from the investigation so the removal can be executed later without retracing the same ground.

## Why This Change Exists

The immediate bug surfaced through `POST /query`.

Example request:

```bash
curl -X 'POST' \
  'http://127.0.0.1:8001/query' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "query": "Show me short trails in Texas"
}'
```

Observed response:

```json
{
  "original_query": "Show me short trails in Texas",
  "interpreted_as": {
    "park_code": "none",
    "state": "TX",
    "source": "TNM",
    "hiked": true,
    "max_length": 3,
    "trail_type": "path",
    "limit": 50
  },
  "function_called": "search_trails",
  "results": {
    "trail_count": 0,
    "total_miles": 0,
    "trails": [],
    "pagination": {
      "limit": 50,
      "offset": 0,
      "total_count": 0,
      "has_next": false,
      "has_prev": false
    }
  }
}
```

The important debugging clue was `trail_type: "path"`.

## Key Architectural Finding

There are two separate things currently called "trail type":

1. TNM stored column: `tnm_hikes.trail_type`
2. API/NLQ filter: `trail_type`, which actually filters OSM `highway` values through `highway_type`

These are related in name only. They are not the same field in practice.

### TNM storage side

The TNM schema has a real `trail_type` column:

- `sql/schema/tnm_hikes.sql`
- `scripts/collectors/tnm_hikes_collector.py`
- `scripts/collectors/tnm_schemas.py`

This column comes from the TNM API field `trailtype`, is stored in Postgres, and appears in some profiling/reporting logic.

### API/NLQ filter side

The user-facing `trail_type` filter does **not** use `tnm_hikes.trail_type`.

Instead:

- `api/queries.py` exposes OSM `highway` as `highway_type`
- TNM rows are projected with `highway_type = NULL`
- filtering by `trail_type` becomes `AND t.highway_type = :trail_type`

That means any query interpreted as both:

- `source=TNM`
- `trail_type=path`

will always produce zero results.

That is exactly why the Texas NLQ request returned no trails despite the DB containing short Texas trails.

## Product Decision Captured Here

Based on inspecting the project data and usages:

- the TNM `trail_type` column does not appear useful
- the OSM `highway`-based filter also does not appear useful enough to preserve
- this is a personal project with no external users
- schema-breaking cleanup is acceptable

Therefore the target end state is:

1. Remove `trail_type` as an NLQ/API/query concept
2. Remove `trail_type` from TNM ingestion and schema
3. Remove profiling, tests, docs, and app leftovers tied to it

## Overall Strategy

Use a phased sequence that fixes runtime behavior first, then simplifies storage and tooling underneath it.

Recommended order:

1. Remove `trail_type` from NLQ
2. Remove `trail_type` from the public API filter
3. Remove app/UI/export leftovers
4. Remove TNM ingestion + DB schema support
5. Remove profiling/reporting references
6. Clean up tests/docs/plans

This order is chosen because:

- it fixes the live bug first
- it shrinks the public surface area before schema work
- it isolates DB-breaking changes to a later phase

## Phase 1: Remove `trail_type` From NLQ

### Goal

Prevent the LLM/parser from ever inventing `trail_type` again.

### Files

- `api/nlq/prompt.py`
- `api/nlq/parser.py`
- `tests/unit/test_nlq_prompt.py`
- `tests/unit/test_nlq_parser.py`
- `tests/eval/golden_queries.json`

### Changes

- Remove `trail_type` from the `search_trails` tool definition in `api/nlq/prompt.py`
- Remove parser normalization for `trail_type` in `api/nlq/parser.py`
- Remove unit tests that validate `trail_type` parsing/acceptance
- Remove golden queries that expect `trail_type` such as footway/path queries

### Why This Is Low Risk

- only affects natural-language interpretation
- does not touch DB schema
- does not change trail retrieval behavior for normal API calls unless they came through NLQ

### Verification

- `POST /query` for "Show me short trails in Texas" should no longer include `trail_type` in `interpreted_as`
- NLQ tests should pass after updated expectations

## Phase 2: Remove `trail_type` From `GET /trails`

### Goal

Stop publicly supporting a filter that is misleading and not useful.

### Files

- `api/main.py`
- `api/queries.py`

### Changes

- Remove the `trail_type` query parameter from `GET /trails`
- Remove the `trail_type` argument from `fetch_trails()`
- Remove the SQL predicate:

```sql
AND t.highway_type = :trail_type
```

- Remove examples/documentation strings that advertise footway/path filtering

### Important Note

This removes the OSM `highway`-based filter, not just the TNM column.

That is intentional. The investigation concluded that the concept is not useful enough anywhere in the project to keep.

### Risk

Low to medium.

It changes the API contract, but this is acceptable for a personal project and removes a broken behavior surface.

### Verification

- `/docs` should no longer show `trail_type` on `GET /trails`
- ordinary trail queries by park/state/length/hiked/source should still work

## Phase 3: Remove App/UI/Export Leftovers

### Goal

Delete dead references after the API/NLQ surface is gone.

### Files

- `streamlit_app/components/nlq.py`
- `streamlit_app/utils/state.py`
- `streamlit_app/utils/export.py`

### Changes

- Remove the NLQ chip that displays `Trail Type: ...`
- Remove `filter_trail_type` session state if it is unused
- Remove `trail_type` fields from CSV/GeoJSON export if they are only vestigial

### Risk

Low.

Mostly cleanup, but should still be checked for missing-key assumptions.

### Verification

- Streamlit app still renders NLQ chips correctly
- exports still work

## Phase 4: Remove TNM `trail_type` From Ingestion and Schema

### Goal

Stop collecting, validating, storing, and indexing the TNM `trail_type` field.

### Files

- `scripts/collectors/tnm_hikes_collector.py`
- `scripts/collectors/tnm_schemas.py`
- `sql/schema/tnm_hikes.sql`

### Changes

- Remove `trailtype -> trail_type` mapping in the TNM collector
- Remove `trail_type` from the allowed `db_columns` set in the collector
- Remove `trail_type` from the Pandera schema
- Remove the `trail_type` column from the TNM schema SQL
- Remove related indexes:
  - `idx_tnm_hikes_trail_type`
  - `idx_tnm_hikes_park_code_trail_type`
- Remove the column comment

### Risk

Medium.

This is the first schema-breaking phase. Existing databases will need either:

- a migration, or
- a rebuild/reset

Given the project context, a rebuild/reset is acceptable.

### Verification

- fresh schema creation works
- TNM collector/pipeline can still write records successfully

## Phase 5: Remove Profiling and Reporting That Depend on TNM `trail_type`

### Goal

Prevent internal analytics from breaking once the column is removed.

### Files

- `profiling/modules/tnm_hikes.py`
- `profiling/queries/tnm_hikes/trail_types.sql`
- `profiling/queries/tnm_hikes/data_quality.sql`
- `profiling/queries/tnm_hikes/trail_statistics.sql`
- `profiling/config.py`

### Changes

- remove TNM trail type breakdown logic entirely, or simplify the profiler to stop reporting it
- remove completeness metrics based on `trail_type`
- remove `typed_trail_count`-style statistics
- remove references to related exported files or config entries

### Risk

Medium, but mostly isolated to internal tooling.

### Verification

- profiling modules run without SQL errors against the new schema

## Phase 6: Tests, Docs, and Historical Plans Cleanup

### Goal

Make the repo internally consistent after the functional changes are complete.

### Files Likely Affected

- `tests/integration/test_api_db.py`
- `tests/unit/test_tnm_schemas.py`
- `tests/test_api.py`
- `docs/`
- `plans/`

### Changes

- remove TNM test fixture values that set `trail_type`
- update tests to stop expecting `trail_type` as a supported filter
- remove docs that describe `trail_type` as a feature
- optionally clean old plan docs that mention `trail_type`

### Note on Historical Docs

Old planning docs do not necessarily need perfect cleanup if they are intentionally archival, but user-facing docs and active implementation notes should not describe `trail_type` as supported after removal.

## File Map by Concern

### Runtime code directly involved in the bug

- `api/nlq/prompt.py`
- `api/nlq/parser.py`
- `api/main.py`
- `api/queries.py`

### Streamlit/UI leftovers

- `streamlit_app/components/nlq.py`
- `streamlit_app/utils/state.py`
- `streamlit_app/utils/export.py`

### TNM ingestion/storage

- `scripts/collectors/tnm_hikes_collector.py`
- `scripts/collectors/tnm_schemas.py`
- `sql/schema/tnm_hikes.sql`

### Profiling/reporting

- `profiling/modules/tnm_hikes.py`
- `profiling/queries/tnm_hikes/trail_types.sql`
- `profiling/queries/tnm_hikes/data_quality.sql`
- `profiling/queries/tnm_hikes/trail_statistics.sql`
- `profiling/config.py`

### Tests and eval fixtures

- `tests/unit/test_nlq_prompt.py`
- `tests/unit/test_nlq_parser.py`
- `tests/eval/golden_queries.json`
- `tests/integration/test_api_db.py`
- `tests/unit/test_tnm_schemas.py`
- `tests/test_api.py`
- `tests/conftest.py`

## Important Implementation Notes

### 1. The bug is not just "bad prompt wording"

Even if the prompt were improved, the current design still allows a logically conflicting combination such as:

- `source=TNM`
- `trail_type=path`

Because TNM rows always project `highway_type` as `NULL` in the combined trail query.

So this should be treated as a design cleanup, not just a prompt tweak.

### 2. `highway_type` is separate from TNM `trail_type`

Do not conflate:

- TNM `trail_type`
- OSM `highway`
- API response field `highway_type`

They happen to overlap in naming but not semantics.

### 3. Phase boundaries are real

The lowest-risk implementation slice is:

- Phase 1
- Phase 2

That pair fixes the active NLQ/API issue without requiring DB surgery.

### 4. Schema breakage is acceptable

This project can tolerate a DB rebuild if that makes Phase 4 simpler and cleaner.

## Suggested Implementation Chunks

### Chunk A: Runtime fix

Do together:

- Phase 1
- Phase 2

Expected outcome:

- NLQ no longer emits `trail_type`
- `/trails` no longer accepts `trail_type`
- the Texas short trails query no longer fails because of that filter

### Chunk B: Surface cleanup

Do next:

- Phase 3

Expected outcome:

- no app/export leftovers mention trail type

### Chunk C: Data model cleanup

Do after runtime stability:

- Phase 4
- Phase 5

Expected outcome:

- TNM no longer stores `trail_type`
- profiling no longer references it

### Chunk D: Final consistency pass

Do last:

- Phase 6

Expected outcome:

- tests, docs, and plan references align with the new reality

## Success Criteria

The work is complete when all of the following are true:

- NLQ cannot produce `trail_type`
- `GET /trails` has no `trail_type` filter
- Streamlit/export code has no meaningful dependency on `trail_type`
- TNM ingestion ignores/discards the TNM `trailtype` field
- the TNM DB schema no longer stores `trail_type`
- profiling and reporting do not query the removed column
- tests and docs no longer describe `trail_type` as supported behavior

## Recommended Next Step

Start with Chunk A:

1. Remove `trail_type` from NLQ
2. Remove `trail_type` from the `/trails` API

That is the lowest-risk path and immediately addresses the user-visible bug that triggered this investigation.

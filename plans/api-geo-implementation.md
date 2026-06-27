# API Geo Endpoints — Implementation Summary

## What Was Done

All 6 steps from the plan in `scratch/api-geo.md` were implemented. The API version was bumped from `1.0.0` to `1.1.0`. **440 tests passing** (85 unit tests in `test_api.py`, plus integration and other test files).

---

## Step-by-Step Changes

### Step 1: Renamed `include_description` → `description`

Mechanical rename across 7 files. No logic changes.

- `api/main.py` — query param name, docstrings, examples
- `api/queries.py` — function param name and usage
- `api/models.py` — Field description text
- `tests/test_api.py` — query strings and function calls
- `tests/conftest.py` — fixture comments
- `tests/integration/test_api_db.py` — query strings and docstring
- `docs/api-tutorial.md` — example URLs and text

### Step 2: Added `park_code` and `state` filters to `/parks`

- `api/main.py` — added `park_code` and `state` query params with validation (`^[a-z]{4}$`, `^[A-Z]{2}$`)
- `api/queries.py` — added WHERE clauses to `fetch_all_parks()` using the existing dynamic WHERE pattern
- 3 new tests: `test_get_parks_filtered_by_park_code`, `test_get_parks_filtered_by_state`, `test_get_parks_filtered_by_park_code_invalid`

### Step 3: Added `boundary` param to `/parks`

- `api/models.py` — added `boundary: dict | None` field to `Park` model
- `api/main.py` — added `boundary` query param (bool, default False)
- `api/queries.py` — conditional LEFT JOIN to `park_boundaries` with `ST_Simplify(geometry, 0.001)`, `json.loads()` parsing. All column references qualified with `parks.` prefix to avoid ambiguity with the JOIN.
- Added `import json` to queries.py
- 2 new tests: `test_get_parks_with_boundary`, `test_get_parks_without_boundary`
- New `sample_parks_boundary_response` fixture in conftest.py

### Step 4: Added `geojson` param to `/trails`

- `api/models.py` — added `geometry: dict | None` field to `Trail` model
- `api/main.py` — added `geojson` query param (bool, default False), added `response_model_exclude_none=True`
- `api/queries.py` — conditional `ST_AsGeoJSON(geometry)` injection into CTEs via string interpolation:
  ```python
  geojson_col = ", ST_AsGeoJSON(geometry) as geojson" if geojson else ""
  geojson_ref = ", geojson" if geojson else ""
  ```
  Applied to: `tnm_trails`, `osm_trails`, `all_trails` UNION, and final SELECT.
- 2 new tests: `test_get_trails_with_geojson`, `test_get_trails_without_geojson`
- New `sample_trails_geojson_response` fixture in conftest.py

### Step 5: New `GET /trails/hiked-points` endpoint

- `api/models.py` — new `HikedPoint` and `HikedPointsResponse` models
- `api/main.py` — new route with `park_code` filter, placed before `/stats`
- `api/queries.py` — new `fetch_hiked_points()` function querying `gmaps_hiking_locations` JOIN `parks` LEFT JOIN `gmaps_hiking_locations_matched`
- 4 new tests: `test_get_hiked_points_no_filter`, `test_get_hiked_points_by_park`, `test_get_hiked_points_empty`, `test_get_hiked_points_invalid_park_code`
- New `sample_hiked_points_response` fixture in conftest.py

### Step 6: Housekeeping

- Bumped version `1.0.0` → `1.1.0` in `api/main.py` (FastAPI metadata and root endpoint)
- Added `hiked_points: "/trails/hiked-points"` to root endpoint listing
- Updated `docs/api-tutorial.md` with new version and endpoint listing
- Updated version assertion in `tests/integration/test_api_db.py`

---

## Bugs Found & Fixed

### 1. Ambiguous column error with `boundary=true`

**Problem:** When using `boundary=true` with any filter (e.g., `park_code`), PostgreSQL threw `AmbiguousColumn` because `park_code` exists in both `parks` and `park_boundaries` tables.

**Fix:** Qualified ALL column references in `fetch_all_parks()` with the `parks.` table prefix — SELECT list, WHERE clauses, and ORDER BY.

### 2. Trails endpoint only showing acad data

**Status:** NOT a code bug. Likely a pipeline/data issue — the user may need to re-run the data pipeline to populate trail data for other parks.

### 3. Integration test version assertion

**Fix:** Updated hardcoded `"1.0.0"` → `"1.1.0"` in `tests/integration/test_api_db.py`.

---

## Files Modified (complete list)

| File | Changes |
|---|---|
| `api/main.py` | Version bump, renamed param, new query params, new route, updated imports/examples |
| `api/queries.py` | Added `import json`, renamed param, new params + boundary JOIN, geojson CTE injection, new `fetch_hiked_points()`, qualified column names |
| `api/models.py` | Updated description text, added `boundary` and `geometry` fields, new `HikedPoint`/`HikedPointsResponse` models |
| `tests/test_api.py` | Renamed params, 11 new tests, updated version assertion, new test class |
| `tests/conftest.py` | Renamed comments, 3 new fixtures |
| `tests/integration/test_api_db.py` | Renamed params, updated version assertion |
| `docs/api-tutorial.md` | Renamed params, updated version and endpoint listing |

---

## Known Issues / Next Steps

1. **Trails data**: Only acad park has trail data — likely needs a pipeline re-run (`scripts/orchestrator.py`), not a code fix.
2. **NLQ integration**: The plan mentions a future "unified + chips" approach for the Streamlit app (use `interpreted_as` + `function_called` from NLQ to set widget state). No NLQ changes were made in this implementation.
3. **Smoke testing**: The geo endpoints (`boundary=true`, `geojson=true`, `/trails/hiked-points`) should be manually verified once the DB has full data.

# Handoff: New Geo API Endpoints & Parks Filtering

## Instructions for New Session

Implement the plan below. Read the referenced files before making changes. Run `pytest tests/` after each step to catch regressions early. Activate the virtualenv first: `source ~/.virtualenvs/nps-hikes/bin/activate`. Bump the API version from `1.0.0` to `1.1.0` in `api/main.py` (appears on lines 68 and 88). Currently 456 tests, all passing.

---

## Background & Design Decisions

This project is a FastAPI REST API backed by PostGIS. We're adding geographic data to the API to support an upcoming Streamlit webapp with an interactive map. Key decisions made during the discussion:

1. **API over direct DB access.** The Streamlit app will be a pure HTTP client to the API. This keeps clean separation, avoids coupling Streamlit to the DB schema, and avoids the hybrid awkwardness of needing HTTP for NLQ but DB for geo data.

2. **Geo data on existing endpoints via opt-in boolean params**, not separate endpoints. Park boundaries go on `/parks?boundary=true` (adds a `boundary` field to each park). Trail geometries go on `/trails?geojson=true` (adds a `geometry` field to each trail). This follows the existing `include_description` pattern, keeps all existing filters working automatically, and avoids proliferating endpoints.

3. **Rename `include_description` to `description`** for consistency. The `include_` prefix is unnecessary — `description=true`, `boundary=true`, `geojson=true` are all unambiguous boolean response-shape toggles. This is a breaking change that touches ~20 references across the codebase.

4. **Add `park_code` and `state` filters to `/parks`** — a gap in the current API. The `/trails` endpoint has both; `/parks` had neither. Needed so the Streamlit app can request a single park's boundary (`/parks?park_code=yose&boundary=true`).

5. **Park boundaries are simplified with `ST_Simplify(geom, 0.001)`** — reduces 22.5 MB of raw boundary data to ~554 KB (97.5% reduction). Avg ~9 KB per park. Mandatory for the API; full-resolution boundaries are never needed for a web map.

6. **Trail geometries are NOT simplified.** Trails are LineStrings averaging ~10 KB each after deduplication (~347 trails total). Per-park payloads are ~200-400 KB. Simplifying trails risks removing meaningful turns. Not worth it at this data size.

7. **New `/trails/hiked-points` endpoint** for GMaps hiking location points. These are the user's personal GPS markers from Google My Maps (299 total, all represent actual hikes). Optional `park_code` filter.

8. **NLQ integration for the Streamlit app** (future, not part of this task): The plan is "unified + chips" — NLQ results update the map AND auto-set the GUI filter widgets to match the interpreted params. The Streamlit app will ignore the NLQ endpoint's `results` and instead use `interpreted_as` + `function_called` to set widget state, then let the normal GUI data-fetching code run with `geojson=true`. One code path for data fetching.

### Geo data sizes (measured from the actual DB)

| Data | Raw size | Simplified | Per-park avg |
|---|---|---|---|
| Park boundaries (62 parks) | 22.5 MB | 554 KB | ~9 KB |
| Trail geometries (347 deduplicated) | ~3.5 MB | N/A (not simplified) | ~200-400 KB |
| GMaps markers (299 points) | negligible | N/A | negligible |

---

## Implementation Plan

### Step 1: Rename `include_description` to `description`

Mechanical rename across all files. No logic changes.

**Files:**
- `api/main.py` — query param name + docstrings/examples (~lines 124, 128, 130, 171, 181)
- `api/queries.py` — function param name + usage (~lines 16, 25, 49, 63, 122)
- `api/models.py` — Field description text (~line 300)
- `tests/test_api.py` — query strings and function calls (~lines 103-104, 782, 803)
- `tests/conftest.py` — fixture comments (~lines 349, 367)
- `tests/integration/test_api_db.py` — query strings (~lines 122, 144)
- `docs/api-tutorial.md` — example URLs (~lines 105, 108)

### Step 2: Add `park_code` and `state` filters to `/parks`

**`api/main.py`** — add query params to `get_all_parks()`:
```python
park_code: str | None = Query(
    default=None, min_length=4, max_length=4, pattern="^[a-z]{4}$",
    description="Filter by park code (e.g., 'yose')",
),
state: str | None = Query(
    default=None, min_length=2, max_length=2, pattern="^[A-Z]{2}$",
    description="Filter by state code (e.g., 'CA')",
),
```
Pass both to `fetch_all_parks()`.

**`api/queries.py`** — `fetch_all_parks()`: add params `park_code: str | None = None, state: str | None = None`. Add WHERE clauses:
```python
if park_code is not None:
    where_clauses.append("park_code = :park_code")
    query_params["park_code"] = park_code

if state is not None:
    where_clauses.append("states LIKE :state")
    query_params["state"] = f"%{state}%"
```
Pattern matches how `/trails` handles these same filters in `fetch_trails()`.

**Tests:** `test_get_parks_filtered_by_park_code`, `test_get_parks_filtered_by_state`, `test_get_parks_filtered_by_park_code_invalid` (422 for bad format).

### Step 3: Add `boundary` param to `/parks`

**`api/models.py`** — update `Park` model, add optional field:
```python
boundary: dict | None = Field(
    None,
    description="Simplified park boundary as GeoJSON geometry (only included when boundary=true)",
)
```

**`api/main.py`** — add query param:
```python
boundary: bool = Query(
    default=False,
    description="Include simplified park boundary GeoJSON in the response",
),
```

**`api/queries.py`** — `fetch_all_parks()`, add param `boundary: bool = False`. When `boundary=True`:
- LEFT JOIN `park_boundaries pb ON parks.park_code = pb.park_code`
- Add `ST_AsGeoJSON(ST_Simplify(pb.geometry, 0.001)) as boundary` to column list
- Parse GeoJSON string into dict via `json.loads()` in the response builder
- When `boundary=False`: query is unchanged (no JOIN, no performance hit)

**Tests:** `test_get_parks_with_boundary` (verify GeoJSON dict), `test_get_parks_without_boundary` (field absent), `test_get_parks_boundary_null_when_missing` (park without boundary returns null).

### Step 4: Add `geojson` param to `/trails`

**`api/models.py`** — update `Trail` model, add optional field:
```python
geometry: dict | None = Field(
    None,
    description="Trail geometry as GeoJSON (only included when geojson=true)",
)
```

**`api/main.py`** — add query param:
```python
geojson: bool = Query(
    default=False,
    description="Include trail geometry GeoJSON in the response",
),
```

**`api/queries.py`** — `fetch_trails()`, add param `geojson: bool = False`. Conditionally add geometry to CTEs using string interpolation:
```python
geojson_col = ", ST_AsGeoJSON(geometry) as geojson" if geojson else ""
geojson_ref = ", geojson" if geojson else ""
```

Apply to each CTE:
- `tnm_trails`: add `{geojson_col}` after `geometry_type`
- `osm_trails`: add `{geojson_col}` after `highway as highway_type`
- `osm_unique`: carries through automatically (`SELECT o.*`)
- `all_trails` UNION: add `{geojson_ref}` to both branches' column lists
- Final SELECT: add `{geojson_ref}` as `t.geojson`

In the response builder, parse `json.loads(row.geojson)` when present.

When `geojson=False` (default): query is identical to today.

**Tests:** `test_get_trails_with_geojson` (verify geometry dict), `test_get_trails_without_geojson` (field absent).

### Step 5: New `GET /trails/hiked-points` endpoint

**`api/models.py`** — new models:
```python
class HikedPoint(BaseModel):
    id: int
    park_code: str
    park_name: str | None
    location_name: str
    latitude: float | None
    longitude: float | None
    matched_trail_name: str | None
    source: str | None

class HikedPointsResponse(BaseModel):
    count: int
    hiked_points: list[HikedPoint]
```

**`api/main.py`** — new route (place after `/trails`):
```python
@app.get("/trails/hiked-points", response_model=HikedPointsResponse, ...)
async def get_hiked_points(
    park_code: str | None = Query(default=None, ...),
) -> dict[str, Any]:
```

**`api/queries.py`** — new `fetch_hiked_points(park_code=None)`:
```sql
SELECT
    g.id, g.park_code, p.park_name, g.location_name,
    g.latitude, g.longitude, m.matched_trail_name, m.source
FROM gmaps_hiking_locations g
JOIN parks p ON g.park_code = p.park_code
LEFT JOIN gmaps_hiking_locations_matched m
    ON g.id = m.gmaps_location_id AND m.matched = true
-- Optional: WHERE g.park_code = :park_code
ORDER BY g.park_code, g.location_name
```

**Tests:** `test_get_hiked_points_no_filter`, `test_get_hiked_points_by_park`, `test_get_hiked_points_empty`, `test_get_hiked_points_invalid_park_code`.

### Step 6: Housekeeping

- Bump API version `1.0.0` to `1.1.0` in `api/main.py` (lines 68 and 88)
- Add `hiked_points: "/trails/hiked-points"` to the root endpoint listing dict in `api/main.py`
- No changes to `api/nlq/prompt.py` — NLQ tools don't need geo params

---

## Key Codebase Patterns to Follow

- **SQLAlchemy `text()` queries** with parameterized inputs (no ORM). See `fetch_trails()` in `api/queries.py` for the pattern.
- **Dynamic WHERE clauses** built as a list, joined with AND. See `fetch_all_parks()`.
- **Pydantic models** with `Field(description=..., examples=[...])` and `model_config` with `json_schema_extra`. See `api/models.py`.
- **`response_model_exclude_none=True`** on route decorators so optional fields like `boundary` and `geometry` don't appear when not requested.
- **Tests use `@patch("api.queries.get_db_engine")`** with `namedtuple` fixtures to mock DB rows. See `tests/conftest.py` for fixture patterns and `tests/test_api.py` for test patterns.
- **Error handling** in route handlers: catch `DatabaseError` (503), `NpsHikesError` (500), generic `Exception` (500).

## DB Tables Referenced

- `parks` — park metadata (park_code PK, lat/lon, states, visit info, description)
- `park_boundaries` — park boundary polygons (park_code PK/FK, geometry MULTIPOLYGON 4326)
- `tnm_hikes` — USGS trail data (permanent_identifier PK, geometry GEOMETRY 4326)
- `osm_hikes` — OpenStreetMap trail data (park_code+osm_id PK, geometry GEOMETRY 4326)
- `gmaps_hiking_locations` — Google My Maps hiking points (id PK, park_code FK, lat/lon)
- `gmaps_hiking_locations_matched` — matched hiking locations to trails (gmaps_location_id PK/FK, matched_trail_name, source, matched boolean)

## Verification

1. Run unit tests: `pytest tests/test_api.py -v` after each step
2. Run full suite: `pytest tests/ -v` — confirm no regressions (currently 456 tests)
3. Manual smoke test (requires DB running via `docker compose up -d`):
   - `curl "http://localhost:8000/parks?park_code=yose&boundary=true" | python3 -m json.tool`
   - `curl "http://localhost:8000/parks?state=CA" | python3 -m json.tool`
   - `curl "http://localhost:8000/trails?park_code=yose&geojson=true&limit=3" | python3 -m json.tool`
   - `curl "http://localhost:8000/trails/hiked-points?park_code=yose" | python3 -m json.tool`
   - `curl "http://localhost:8000/parks?description=true" | python3 -m json.tool`

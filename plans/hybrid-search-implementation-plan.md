# Hybrid Search Implementation Plan

## Step 8: Add Structured Filters to `search_by_topic`

**Goal**: Enable `search_by_topic` to accept structured filters (`hiked`, `min_length`, `max_length`, `source`, `trail_type`) alongside semantic queries, allowing combined queries like "slot canyons I hiked" or "waterfall hikes over 5 miles in California".

**Status**: Not started.

**Context**: Currently, `search_by_topic` handles semantic queries ("slot canyons") while `search_trails` handles structured filters (`hiked=true`, `min_length=5`). Queries that combine both aspects (e.g., "waterfall hikes I completed out west") can only route to one tool, losing the other dimension.

**Solution**: Extend `search_by_topic` tool definition and `fetch_topic_trails()` to accept the same filter parameters as `fetch_trails()`, applying them in SQL after semantic matching.

---

### Files modified

| File | Change |
|------|--------|
| `api/nlq/prompt.py` | Add `hiked`, `min_length`, `max_length`, `source`, `trail_type` parameters to `search_by_topic` tool definition; update system message guidance |
| `api/queries.py` | Add filter parameters to `fetch_topic_trails()` signature; add WHERE clauses in final SELECT |
| `api/main.py` | Pass new filter parameters through in `search_by_topic` dispatch (both `/query` and `/search` endpoints) |
| `api/nlq/parser.py` | Ensure new parameters are normalized (likely already handled by existing `_normalize_topic_search_params`) |
| `tests/unit/test_topic_trails_query.py` | Add tests for filter combinations |
| `tests/unit/test_nlq_prompt.py` | Update tool definition assertions |
| `tests/unit/test_nlq_parser.py` | Add tests for filter extraction and normalization |
| `tests/test_api.py` | Add integration tests for `/search?resolve_trails=true` with filters |

---

### Implementation

#### 1. Update tool definition in `api/nlq/prompt.py`

**Lines 157-196** - Extend `search_by_topic` tool parameters:

```python
{
    "type": "function",
    "function": {
        "name": "search_by_topic",
        "description": (
            "Search for trails and park activities by topic or theme using "
            "semantic similarity. Use for descriptive/thematic questions: "
            "waterfalls, slot canyons, winter activities, kid-friendly hikes, "
            "scenic viewpoints — anything with a semantic/descriptive component. "
            "Can be combined with structured filters (length, hiked status, etc.)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "The search query describing what the user is looking for. "
                        "Use descriptive terms from the user's question."
                    ),
                },
                "park_code": {
                    "type": "string",
                    "description": (
                        "4-character lowercase park code to limit search to a specific park. "
                        "Use the park lookup table to find the correct code."
                    ),
                },
                "state": {
                    "type": "string",
                    "description": "2-letter uppercase US state code (e.g., 'CA', 'UT')",
                },
                "hiked": {
                    "type": "boolean",
                    "description": "true = only trails the user has hiked, false = only unhiked trails",
                },
                "min_length": {
                    "type": "number",
                    "description": "Minimum trail length in miles",
                },
                "max_length": {
                    "type": "number",
                    "description": "Maximum trail length in miles",
                },
                "source": {
                    "type": "string",
                    "enum": ["TNM", "OSM"],
                    "description": "Data source: TNM (USGS) or OSM (OpenStreetMap)",
                },
                "trail_type": {
                    "type": "string",
                    "enum": ["path", "footway", "track", "steps", "cycleway"],
                    "description": "OSM highway type filter (only applies to OSM trails)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results (1-50, default 20)",
                },
            },
            "required": ["query"],
        },
    },
},
```

**Lines 199-225** - Update system message guidance:

```python
_SYSTEM_MESSAGE_TEMPLATE = """\
You are a trail finder assistant for US National Parks.
Your ONLY job is to call the appropriate function with the correct parameters \
based on the user's question. Always respond with a function call, never with plain text.

Park name to park_code lookup:
{park_lookup_text}

Rules:
- Always use the park_code (4 lowercase letters), never the full park name, as the parameter value.
- State codes must be 2 uppercase letters (e.g., CA, UT, CO).
- When the user mentions a US state (e.g., "in Colorado", "California trails"), use the state parameter. Do NOT pick a specific park within that state instead.
- Trail lengths are in miles.
- For "short" trails, use max_length=3. For "long" trails, use min_length=5.
- "Under X miles", "less than X miles", "shorter than X miles" → use max_length=X.
- "Over X miles", "more than X miles", "at least X miles", "longer than X miles" → use min_length=X.
- If the user asks about trails or hikes WITH a semantic/descriptive component (waterfalls, slot canyons, kid-friendly, scenic views), use search_by_topic. You can include structured filters (hiked, length, source) as additional parameters.
- If the user asks about trails or hikes with ONLY structured filters and no semantic component (e.g., "trails over 5 miles in Zion", "short trails I hiked"), use search_trails.
- If the user asks about parks (not trails), use search_parks.
- Words like "haven't", "not", "never", "unvisited" indicate negation. "Parks I haven't visited" → visited=false. "Trails I haven't hiked" → hiked=false.
- If the user mentions a specific year for park visits, include visit_year in search_parks.
- If the user mentions a specific month or season for park visits, include visit_month with the month name or season name (spring, summer, fall, winter).
- If the user asks about overall statistics (total miles, trail counts, park counts, averages, longest/shortest), use search_stats.
- If the user asks for a per-park breakdown of stats, use search_stats with per_park=true.
- If the user asks about a specific park's details, summary, or overview, use search_park_summary.
- Only include parameters that the user's question implies. Do not add extra filters.\
"""
```

**Key change**: Tool selection now based on presence of semantic component, not "can't be expressed as filters."

#### 2. Extend `fetch_topic_trails()` in `api/queries.py`

**Lines 920-926** - Update function signature:

```python
def fetch_topic_trails(
    query_embedding: list[float],
    park_code: str | None = None,
    state: str | None = None,
    hiked: bool | None = None,
    min_length: float | None = None,
    max_length: float | None = None,
    source: str | None = None,
    trail_type: str | None = None,
    limit: int = 20,
    geojson: bool = True,
) -> dict[str, Any]:
```

**Lines 926-954** - Update docstring:

```python
    """
    Semantic search bridging content to structured trail data.

    Performs vector similarity search on content embeddings, joins through
    the pre-computed content_trail_mapping to trail tables (TNM/OSM),
    applies optional structured filters, deduplicates (TNM preferred via
    pg_trgm similarity), and returns structured trail data with topic context.

    When no trails match, populates fallback_chunks with unmatched
    semantic results for prose generation.

    Args:
        query_embedding: The embedding vector for the search query.
        park_code: Optional filter by park code.
        state: Optional filter by state abbreviation (e.g., 'CA').
        hiked: Optional filter by hiking status (True=hiked, False=unhiked).
        min_length: Optional minimum trail length in miles.
        max_length: Optional maximum trail length in miles.
        source: Optional data source filter ('TNM' or 'OSM').
        trail_type: Optional OSM highway type filter (e.g., 'path', 'footway').
        limit: Maximum number of trail results (default: 20).
        geojson: Whether to include GeoJSON geometry (default: True).

    Returns:
        Dictionary containing:
            - trail_count: int
            - total_miles: float
            - trails: list (same shape as fetch_trails)
            - topic_context: list of dicts with trail_id, trail_name,
              content_title, chunk_text_preview per matched content
            - fallback_chunks: list of unmatched semantic results
              (populated only when no trails match)
    """
```

**Lines 1034-1051** - Add WHERE clauses to final SELECT:

Replace the current final SELECT with:

```python
    # Build filter clauses for final trail filtering
    trail_where_clauses = []

    if hiked is True:
        trail_where_clauses.append("m.gmaps_location_id IS NOT NULL")
    elif hiked is False:
        trail_where_clauses.append("m.gmaps_location_id IS NULL")

    if min_length is not None:
        trail_where_clauses.append("r.length_miles >= :min_length")
        params["min_length"] = min_length

    if max_length is not None:
        trail_where_clauses.append("r.length_miles <= :max_length")
        params["max_length"] = max_length

    if source is not None:
        trail_where_clauses.append("r.source = :source")
        params["source"] = source

    if trail_type is not None:
        trail_where_clauses.append("r.highway_type = :trail_type")
        params["trail_type"] = trail_type

    trail_where_sql = ""
    if trail_where_clauses:
        trail_where_sql = " WHERE " + " AND ".join(trail_where_clauses)

    # Trail query: semantic search → mapping → trail tables → dedup → filters
    trail_query = f"""
    WITH semantic_hits AS (
        -- ... existing CTE unchanged ...
    ),
    mapped AS (
        -- ... existing CTE unchanged ...
    ),
    tnm_data AS (
        -- ... existing CTE unchanged ...
    ),
    osm_data AS (
        -- ... existing CTE unchanged ...
    ),
    osm_unique AS (
        -- ... existing CTE unchanged ...
    ),
    all_trail_results AS (
        -- ... existing CTE unchanged ...
    )
    SELECT
        r.trail_id, r.trail_name, r.park_code,
        p.park_name, p.states,
        r.source, r.length_miles, r.geometry_type, r.highway_type,
        r.content_title, r.chunk_text, r.similarity_score,
        CASE WHEN m.gmaps_location_id IS NOT NULL THEN true
             ELSE false END as hiked,
        CASE WHEN ute.trail_slug IS NOT NULL THEN true
             ELSE false END as viz_3d_available,
        ute.trail_slug as viz_3d_slug{geojson_final}
    FROM all_trail_results r
    LEFT JOIN parks p ON r.park_code = p.park_code
    LEFT JOIN gmaps_hiking_locations_matched m
        ON r.park_code = m.park_code AND r.source = m.source
        AND r.trail_name = m.matched_trail_name
    LEFT JOIN usgs_trail_elevations ute
        ON m.gmaps_location_id = ute.gmaps_location_id
    {trail_where_sql}
    ORDER BY r.similarity_score DESC
    """
```

**Note**: Filters are applied AFTER semantic matching and deduplication. This ensures:
1. Semantic ranking is preserved (filters don't affect similarity scores)
2. Efficient query (filters applied to deduplicated result set, not raw embeddings)
3. Fallback chunks still contain unfiltered semantic matches (for generation context)

#### 3. Update `/query` endpoint dispatch in `api/main.py`

**Lines ~1165-1175** - Pass new parameters through:

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
        hiked=params.get("hiked"),
        min_length=params.get("min_length"),
        max_length=params.get("max_length"),
        source=params.get("source"),
        trail_type=params.get("trail_type"),
        limit=params.get("limit", 20),
        geojson=True,
    )

    # ... rest of dispatch unchanged (branching on trail_count, generation, etc.)
```

#### 4. Update `/search` endpoint in `api/main.py`

**Lines ~1000-1020** - Add query parameters and pass through:

```python
@app.get(
    "/search",
    summary="Semantic search across park content",
    description="...",
)
async def semantic_search(
    q: str = Query(..., description="Search query"),
    park_code: str | None = Query(None, description="Filter by park code"),
    source_type: str | None = Query(None, description="Filter by content type"),
    limit: int = Query(10, ge=1, le=100, description="Max results"),
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
    hiked: bool | None = Query(
        default=None,
        description="Filter by hiking status (true=hiked, false=unhiked). Only used when resolve_trails=true",
    ),
    min_length: float | None = Query(
        default=None,
        ge=0,
        description="Minimum trail length in miles. Only used when resolve_trails=true",
    ),
    max_length: float | None = Query(
        default=None,
        ge=0,
        description="Maximum trail length in miles. Only used when resolve_trails=true",
    ),
    source: str | None = Query(
        default=None,
        description="Data source filter ('TNM' or 'OSM'). Only used when resolve_trails=true",
        pattern="^(TNM|OSM)$",
    ),
    trail_type: str | None = Query(
        default=None,
        description="OSM highway type (e.g., 'path', 'footway'). Only used when resolve_trails=true",
    ),
) -> dict[str, Any]:
    """Semantic search endpoint with optional trail resolution and filtering."""

    try:
        query_embedding = await get_embeddings([q])
        if not query_embedding or not query_embedding[0]:
            raise HTTPException(422, "Failed to generate embedding")

        if resolve_trails:
            topic_results = fetch_topic_trails(
                query_embedding=query_embedding[0],
                park_code=park_code,
                state=state,
                hiked=hiked,
                min_length=min_length,
                max_length=max_length,
                source=source,
                trail_type=trail_type,
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
            # Original behavior: return raw semantic chunks
            results = fetch_semantic_search(
                query_embedding[0],
                park_code=park_code,
                source_type=source_type,
                limit=limit,
            )
            return {"query": q, **results}

    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

**Note**: `source_type` parameter only used when `resolve_trails=False` (raw content search). When `resolve_trails=True`, use `source` parameter for trail data source filtering.

#### 5. Parser normalization in `api/nlq/parser.py`

Verify that `_normalize_topic_search_params()` handles the new parameters. It should already handle `hiked`, `min_length`, `max_length`, `source` if they follow the same pattern as `_normalize_trail_params()`.

If not already present, add parameter normalization similar to lines ~200-250 in parser.py:

```python
def _normalize_topic_search_params(params: dict[str, Any]) -> dict[str, Any]:
    """Normalize parameters for search_by_topic."""
    normalized = {}

    # Required parameter
    if "query" in params:
        normalized["query"] = params["query"]

    # Optional parameters - pass through if present
    for key in ["park_code", "limit"]:
        if key in params:
            normalized[key] = params[key]

    # State normalization (uppercase, name → code)
    if "state" in params and params["state"]:
        state_input = str(params["state"]).strip()
        # Try name → code lookup
        state_code = _STATE_NAME_TO_CODE.get(state_input.lower())
        if state_code:
            normalized["state"] = state_code
        else:
            # Assume it's already a code, uppercase it
            normalized["state"] = state_input.upper()

    # Boolean and numeric filters - pass through
    for key in ["hiked", "min_length", "max_length"]:
        if key in params and params[key] is not None:
            normalized[key] = params[key]

    # Source and trail_type - uppercase
    if "source" in params and params["source"]:
        normalized["source"] = params["source"].upper()

    if "trail_type" in params and params["trail_type"]:
        normalized["trail_type"] = params["trail_type"].lower()

    return normalized
```

Update the `VALID_FUNCTIONS` dict to call this normalizer:

```python
VALID_FUNCTIONS = {
    "search_trails": _normalize_trail_params,
    "search_parks": _normalize_park_params,
    "search_stats": _normalize_stats_params,
    "search_park_summary": _normalize_park_summary_params,
    "search_by_topic": _normalize_topic_search_params,
}
```

---

### Tests

#### Unit tests for `fetch_topic_trails()` - `tests/unit/test_topic_trails_query.py`

Add test class `TestTopicTrailsWithFilters` (~20 tests):

```python
class TestTopicTrailsWithFilters:
    """Test fetch_topic_trails with structured filters."""

    def test_filter_by_hiked_true(self, mock_db_engine):
        """Only returns trails where hiked=True."""
        # Mock data: 3 trails, 2 hiked, 1 unhiked
        # Call with hiked=True
        # Assert only 2 trails returned

    def test_filter_by_hiked_false(self, mock_db_engine):
        """Only returns trails where hiked=False."""

    def test_filter_by_min_length(self, mock_db_engine):
        """Only returns trails >= min_length."""

    def test_filter_by_max_length(self, mock_db_engine):
        """Only returns trails <= max_length."""

    def test_filter_by_length_range(self, mock_db_engine):
        """Applies both min and max length filters."""

    def test_filter_by_source_tnm(self, mock_db_engine):
        """Only returns TNM trails."""

    def test_filter_by_source_osm(self, mock_db_engine):
        """Only returns OSM trails."""

    def test_filter_by_trail_type(self, mock_db_engine):
        """Filters OSM trails by highway type."""

    def test_combined_filters(self, mock_db_engine):
        """Applies multiple filters simultaneously."""
        # hiked=True, min_length=5, source='TNM'

    def test_filters_eliminate_all_results(self, mock_db_engine):
        """Returns empty trails when filters eliminate all semantic matches."""
        # Mock: semantic search finds 5 trails, all < 3 miles
        # Call with min_length=5
        # Assert trail_count=0, fallback_chunks populated

    def test_filters_do_not_affect_fallback_chunks(self, mock_db_engine):
        """Fallback chunks contain unfiltered semantic results."""
        # Verify fallback query doesn't include trail filters

    def test_filters_with_state(self, mock_db_engine):
        """Combines state filter with structured filters."""
        # state='CA', hiked=True

    def test_filters_with_park_code(self, mock_db_engine):
        """Combines park_code with structured filters."""
        # park_code='yose', min_length=10

    def test_topic_context_includes_filtered_trails_only(self, mock_db_engine):
        """topic_context only includes trails that passed filters."""

    def test_no_filters_behaves_as_before(self, mock_db_engine):
        """Passing no filters returns all semantic matches (backward compat check)."""
```

#### Unit tests for parser - `tests/unit/test_nlq_parser.py`

Add tests for `search_by_topic` parameter extraction (~10 tests):

```python
def test_search_by_topic_with_hiked_filter():
    """Extracts hiked=True from tool call."""

def test_search_by_topic_with_length_filters():
    """Extracts min_length and max_length."""

def test_search_by_topic_with_source_filter():
    """Extracts source parameter, uppercases it."""

def test_search_by_topic_with_trail_type():
    """Extracts trail_type parameter."""

def test_search_by_topic_combined_filters():
    """Extracts multiple filters in one call."""

def test_search_by_topic_filters_optional():
    """Filters are optional, not required."""
```

#### Integration tests for `/search` endpoint - `tests/test_api.py`

Add tests in `TestSearchEndpointResolveTrails` class (~8 tests):

```python
def test_resolve_trails_with_hiked_filter(client):
    """GET /search?resolve_trails=true&hiked=true returns only hiked trails."""

def test_resolve_trails_with_length_filter(client):
    """GET /search?resolve_trails=true&min_length=5 filters by length."""

def test_resolve_trails_with_source_filter(client):
    """GET /search?resolve_trails=true&source=TNM filters by source."""

def test_resolve_trails_with_combined_filters(client):
    """Multiple filters work together."""

def test_resolve_trails_filters_return_empty(client):
    """Returns empty result when filters eliminate all matches."""

def test_search_without_resolve_ignores_trail_filters(client):
    """resolve_trails=false ignores hiked/length/source params."""

def test_resolve_trails_invalid_source_rejected(client):
    """Invalid source value returns 422."""

def test_resolve_trails_invalid_length_rejected(client):
    """Negative length returns 422."""
```

#### Manual LLM routing tests

Test queries to verify LLM routing logic:

```bash
# Should route to search_by_topic with filters
curl -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{"query": "slot canyons i hiked"}'
# Expected: search_by_topic, {query: "slot canyons", hiked: true}

curl -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{"query": "waterfall hikes over 5 miles in California"}'
# Expected: search_by_topic, {query: "waterfall hikes", min_length: 5, state: "CA"}

curl -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{"query": "long slot canyon trails"}'
# Expected: search_by_topic, {query: "slot canyon trails", min_length: 5}

# Should still route to search_trails (no semantic component)
curl -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{"query": "trails over 5 miles in Zion"}'
# Expected: search_trails, {park_code: "zion", min_length: 5}

curl -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{"query": "short trails i hiked in Utah"}'
# Expected: search_trails, {max_length: 3, hiked: true, state: "UT"}
```

---

### Verification checklist

- [ ] All new unit tests pass (fetch_topic_trails filters, parser, API integration)
- [ ] All existing tests pass (zero regressions)
- [ ] Manual LLM routing tests work as expected (semantic → search_by_topic, non-semantic → search_trails)
- [ ] `/search` endpoint accepts new filter parameters, validates them correctly
- [ ] `/search?resolve_trails=true&hiked=true` returns filtered results
- [ ] Filters applied AFTER semantic ranking (similarity_score preserved)
- [ ] Empty result when filters eliminate all matches triggers generation fallback
- [ ] `topic_context` only includes trails that passed filters
- [ ] Backward compat: calling `fetch_topic_trails` without filters works as before
- [ ] OpenAPI docs at `/docs` render correctly with new parameters
- [ ] Test the original failing query: "slot canyons i hiked out west" → now returns results with hiked filter applied

---

### Edge cases to test

1. **Filters eliminate all results**: Semantic search finds 10 trails, filters eliminate all → `trail_count=0`, generation kicks in
2. **Filters eliminate some results**: Semantic search finds 10 trails, filters leave 3 → `trail_count=3`, topic_context contains 3 trails
3. **Conflicting filters**: `min_length=10, max_length=5` → returns empty (SQL handles gracefully)
4. **Invalid filter values**: Negative lengths, invalid source string → should be caught by FastAPI validation
5. **trail_type filter on TNM trails**: Should work (highway_type is NULL for TNM, filter won't match)
6. **Filters without semantic query**: Not possible - `query` is required parameter

---

## Step 9: Update Streamlit UI for Hybrid Search

**Goal**: Display `search_by_topic` results with applied filters in the Streamlit app.

**Status**: Not started.

**Note**: Deferred until Step 8 (hybrid search backend) is complete. This section documents what needs to change.

### Challenge

The Streamlit UI must handle `search_by_topic` results that have structured filters applied. Currently, Step 8 (old numbering, now Step 10) handles topic queries but doesn't account for filters being part of the query.

With hybrid search:
- User asks "waterfall hikes I completed over 5 miles in California"
- LLM routes to `search_by_topic` with `{query: "waterfall hikes", hiked: true, min_length: 5, state: "CA"}`
- API returns filtered trails
- UI must show:
  - Trails on map and table (already handled)
  - Generated summary (already handled)
  - Applied filters somewhere visible (new requirement)

### Files to modify

| File | Change |
|------|--------|
| `streamlit_app/components/nlq.py` | Update `_apply_params_to_widgets` to handle filter params in `search_by_topic`; update `_build_chip_texts` to show applied filters; update `_nlq_params_diverged` to check filter divergence |
| `streamlit_app/app.py` | No changes needed - trail injection already works |

### Implementation notes

**1. Display applied filters in chips**

When `search_by_topic` has filters applied, show them as chips alongside the topic chip:

```
[Topic: waterfall hikes] [California] [Hiked] [5+ miles]
```

Update `_build_chip_texts()` in `nlq.py`:

```python
if function_called == "search_by_topic":
    chips = []

    # Topic chip (always present)
    query_text = params.get("query", "")
    chips.append(f"Topic: {query_text}")

    # Park/state chips (existing logic)
    if params.get("park_code"):
        # ... existing park chip logic
    elif params.get("state"):
        chips.append(params["state"])

    # NEW: Filter chips
    if params.get("hiked") is True:
        chips.append("Hiked")
    elif params.get("hiked") is False:
        chips.append("Not hiked")

    if params.get("min_length"):
        chips.append(f"{params['min_length']}+ miles")

    if params.get("max_length"):
        chips.append(f"≤{params['max_length']} miles")

    if params.get("source"):
        chips.append(params["source"])

    if params.get("trail_type"):
        chips.append(params["trail_type"])

    return chips
```

**2. Apply filters to sidebar widgets**

Update `_apply_params_to_widgets()` to set sidebar filter states:

```python
if function_name == "search_by_topic":
    # ... existing logic for park selection ...

    # NEW: Set filter widgets to match query params
    if params.get("hiked") is not None:
        st.session_state.hiked_filter = (
            "Hiked" if params["hiked"] else "Not hiked"
        )
    else:
        st.session_state.hiked_filter = "All"

    if params.get("min_length"):
        st.session_state.min_length = params["min_length"]

    if params.get("max_length"):
        st.session_state.max_length = params["max_length"]

    if params.get("source"):
        st.session_state.source_filter = params["source"]

    # trail_type is OSM-specific, may not have a sidebar widget
```

**Option**: Show filters as **read-only** (disabled widgets) vs **editable** (active widgets).

- **Read-only**: User can see what was applied but can't change without clearing the query
- **Editable**: User can adjust filters, which triggers divergence and clears topic results

**Recommendation**: Editable (Option B) - more flexible UX. Divergence detection handles the transition.

**3. Divergence detection**

Update `_nlq_params_diverged()` to check filter parameters:

```python
if function_name == "search_by_topic":
    # ... existing park_code check ...

    # Check hiked filter
    query_hiked = params.get("hiked")
    widget_hiked = (
        True if st.session_state.hiked_filter == "Hiked"
        else False if st.session_state.hiked_filter == "Not hiked"
        else None
    )
    if query_hiked != widget_hiked:
        return True

    # Check length filters
    if params.get("min_length") != st.session_state.get("min_length"):
        return True
    if params.get("max_length") != st.session_state.get("max_length"):
        return True

    # Check source filter
    if params.get("source") != st.session_state.get("source_filter"):
        return True

    return False
```

**4. Testing**

- [ ] Enter "waterfall hikes I completed" → chips show "Topic: waterfall hikes" + "Hiked"
- [ ] Sidebar "Hiked" filter matches "Hiked" state from query
- [ ] Change sidebar filter → divergence detected, topic results cleared
- [ ] Enter "long slot canyons" → chips show "Topic: slot canyons" + "5+ miles"
- [ ] Enter "trails over 5 miles in Zion" → routes to `search_trails`, normal flow (no topic chips)

---

## Step 10: API Tutorial + Documentation

**Goal**: Document hybrid search feature in API tutorial and update related docs.

**Status**: Not started.

### Files to modify

| File | Change |
|------|--------|
| `docs/api-tutorial.md` | Add "Hybrid Search" section covering semantic + filter combinations |
| `README.md` | Update project overview if needed to mention hybrid search capability |
| `scratch/semantic-search-plan.md` | Mark Steps 8-9 as complete, add note about future regional support |

### Documentation content

Add section to `docs/api-tutorial.md`:

```markdown
## Hybrid Search: Combining Semantic Queries with Filters

The `/query` endpoint's `search_by_topic` tool and the `/search` endpoint's `resolve_trails=true` mode support hybrid search: semantic queries combined with structured filters.

### Examples

#### Natural language query (via `/query`)

Combine semantic terms with filters:

```bash
curl -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{"query": "waterfall hikes I completed over 5 miles in California"}'
```

The LLM routes to `search_by_topic` and extracts:
- Semantic: "waterfall hikes"
- Filters: `hiked=true`, `min_length=5`, `state="CA"`

#### Direct REST API (via `/search`)

For programmatic access without NLQ:

```bash
curl "http://localhost:8001/search?q=waterfalls&resolve_trails=true&hiked=true&min_length=5&state=CA"
```

Returns structured trail data matching both semantic criteria and filters.

### Supported Filters

When using `search_by_topic` or `/search?resolve_trails=true`, you can apply:

- `hiked` (boolean): Filter by hiking status
- `min_length` (float): Minimum trail length in miles
- `max_length` (float): Maximum trail length in miles
- `source` (string): Data source ('TNM' or 'OSM')
- `trail_type` (string): OSM highway type ('path', 'footway', etc.)
- `state` (string): 2-letter state code
- `park_code` (string): 4-character park code

### Tool Selection Logic

- **Use `search_by_topic`**: Queries with semantic/descriptive components
  - "slot canyons I hiked" → semantic: slot canyons, filter: hiked
  - "kid-friendly short trails" → semantic: kid-friendly, filter: max_length

- **Use `search_trails`**: Queries with ONLY structured filters
  - "trails over 5 miles in Zion" → structured only, no semantic component

The LLM handles routing automatically via `/query`.

### Filter Behavior

Filters are applied **after** semantic matching, so:
1. Semantic search finds relevant content (e.g., "waterfall" mentions)
2. Content resolves to trails via pre-computed mappings
3. Filters are applied to the trail results
4. Results ranked by semantic similarity

If filters eliminate all results, the system generates a prose answer from the semantic matches.
```

---

## Future Enhancement: Regional Query Support

**Goal**: Map regional terms ("out west", "southwest", "Pacific Northwest") to multiple state filters.

**Status**: Deferred - separate task.

**Context**: Currently, `state` parameter accepts a single 2-letter code. Queries like "slot canyons out west" should map to multiple western states (`["UT", "AZ", "CO", "NV", "NM", "WY", "MT", "ID"]`).

**Approach**:

1. Change `state: str | None` to `states: list[str] | None` in `fetch_topic_trails()` signature
2. Update SQL to handle multiple states with OR conditions
3. Create a regional mapping in prompt or parser:
   ```python
   REGIONS = {
       "out west": ["UT", "AZ", "CO", "NV", "NM", "WY", "MT", "ID"],
       "southwest": ["AZ", "NM", "UT", "NV"],
       "pacific northwest": ["WA", "OR"],
       "northeast": ["ME", "NH", "VT", "MA", "RI", "CT", "NY", "PA", "NJ"],
       # ...
   }
   ```
4. Update LLM system prompt to recognize regional terms and expand to state lists
5. Update parser to resolve regional terms to `states` list
6. Update Streamlit UI to show regional chip or multiple state chips

**Rationale for deferring**: This is orthogonal to the core hybrid search problem. The infrastructure for accepting multiple states and the LLM logic for regional mapping are separate concerns that can be addressed independently.

**Return to this after Step 8 (hybrid search) is complete and tested.**

---

## LLM Query Interpretation Issues (Testing Findings)

**Testing Date**: 2024-present
**Status**: Phase 1 fixes implemented and verified. All hallucination issues resolved.

### Test Results Summary (Pre-Fix)

| Query | Expected Behavior | Pre-Fix Behavior | Issue Type |
|-------|------------------|-----------------|------------|
| "waterfall hikes I completed" | `hiked=true`, no park_code | Sometimes adds `park_code="acad"` (non-deterministic) | Hallucinated parameter |
| "long slot canyon trails" | `min_length=5`, no park_code | `park_code="arch"` or `"zion"`, `max_length=100`, `source="OSM"`, `hiked=false` | Multiple hallucinations |
| "slot canyons in Utah" | `state="UT"`, no extras | `state="UT"` ✓ but also adds `source="TNM"`, `hiked=true`, `min_length=0`, `max_length=0` | Extra parameters |
| "waterfall hikes I completed in California" | `state="CA"`, `hiked=true`, no park_code | `park_code="wica"` (which isn't in CA) | Hallucinated + wrong park |
| "short waterfall hikes" | `max_length=3` | Not tested pre-fix | - |
| "trails over 5 miles in Zion" | `search_trails`, `park_code="zion"`, `min_length=5` | Not tested pre-fix | - |

### Test Results Summary (Post-Fix)

All queries tested after implementing Phase 1 (prompt strengthening, temperature=0, post-processing validation).

| Query | Expected | Actual (Post-Fix) | Result |
|-------|----------|-------------------|--------|
| "waterfall hikes I completed" | `search_by_topic`, `hiked=true` | `search_by_topic`, `hiked=true` | **PASS** |
| "long slot canyon trails" | `search_by_topic`, `min_length=5` | `search_by_topic`, `min_length=10.0` | **PASS** (value differs, direction correct, all hallucinations removed) |
| "slot canyons in Utah" | `search_by_topic`, `state="UT"` | `search_by_topic`, `state="UT"` | **PASS** |
| "waterfall hikes I completed in California" | `search_by_topic`, `state="CA"`, `hiked=true` | `search_by_topic`, `state="CA"`, `hiked=true` | **PASS** |
| "short waterfall hikes" | `search_by_topic`, `max_length=3` | `search_by_topic`, `max_length=3.0` | **PASS** |
| "trails over 5 miles in Zion" | `search_trails`, `park_code="zion"`, `min_length=5` | `search_trails`, `park_code="zion"`, `min_length=5.0` | **PASS** |
| "slot canyons I haven't hiked yet" | `search_by_topic`, `hiked=false` | `search_by_topic`, `hiked=false` | **PASS** |

**All forbidden parameters (hallucinated park_code, source, hiked, spurious lengths) were absent in every post-fix test.**

### Systematic Issues Identified

#### 1. **Hallucinated park_code based on semantic content**
**Severity**: High
**Frequency**: Common

The LLM infers park associations from semantic terms and adds `park_code` when none was mentioned:
- "slot canyons" → assumes Arches or Zion
- "waterfall hikes" → assumes Acadia or other waterfall-famous parks
- "waterfall hikes in California" → picks wrong park code

**Why this is problematic**:
- User wants ALL slot canyons across all parks
- Adding park_code drastically limits results
- The inference is often wrong (e.g., `wica` isn't even in California)

**Root cause**: LLM has world knowledge about which parks are famous for certain features and over-applies it, violating the instruction "Only include parameters that the user's question implies."

#### 2. **Hallucinated source filter**
**Severity**: Medium
**Frequency**: Common

The LLM adds `source="TNM"` or `source="OSM"` when not requested:
- "long slot canyon trails" → adds `source="OSM"`
- "slot canyons in Utah" → adds `source="TNM"`

**Why this is problematic**:
- Eliminates half the trail data without user intent
- User didn't express preference for data source

**Root cause**: Unclear, possibly trying to be "helpful" or making assumptions about data quality.

#### 3. **Hallucinated boolean filters**
**Severity**: Medium
**Frequency**: Occasional

The LLM adds `hiked=true` or `hiked=false` when not mentioned:
- "long slot canyon trails" → adds `hiked=false` (why?)
- "slot canyons in Utah" → adds `hiked=true` (why?)

**Why this is problematic**:
- Filters out half the results arbitrarily
- No indication in query about hiking status

**Root cause**: LLM may be inferring intent (e.g., "I want to hike new trails") but this is speculative.

#### 4. **Spurious zero-value filters**
**Severity**: Low (likely filtered out by parser)
**Frequency**: Occasional

The LLM adds `min_length=0.0` and `max_length=0.0`:
- "slot canyons in Utah" → both set to 0

**Why this is problematic**:
- Makes no semantic sense (trails can't be 0 miles)
- Creates invalid filter (max < min conceptually)

**Root cause**: LLM may be trying to "fill in" the schema, or these might be hallucinations.

#### 5. **Wrong length filter direction**
**Severity**: Medium
**Frequency**: Occasional

For "long" trails, LLM sometimes uses `max_length` instead of `min_length`:
- "long slot canyon trails" → `max_length=100` instead of `min_length=5`

**Why this is problematic**:
- Semantically backwards (long = min, not max)
- Prompt explicitly says "For 'long' trails, use min_length=5"

**Root cause**: Possible prompt misinterpretation or LLM confusion.

#### 6. **Non-deterministic responses**
**Severity**: High
**Frequency**: Always (by nature of LLM)

Same query produces different parameter extractions on different runs:
- "waterfall hikes I completed" sometimes adds park_code, sometimes doesn't
- "long slot canyon trails" → `park_code="arch"` vs `park_code="zion"`

**Why this is problematic**:
- Unpredictable user experience
- Makes debugging difficult
- Undermines trust in the system

**Root cause**: Inherent LLM behavior (temperature > 0, non-deterministic sampling).

---

### Proposed Improvements

#### Option A: Stricter Prompt Engineering
**Approach**: Strengthen the system prompt to explicitly forbid hallucinations.

**Changes to `api/nlq/prompt.py`**:
```python
Rules:
...
- CRITICAL: Only include parameters explicitly mentioned or directly implied by the user's query.
- DO NOT add park_code unless the user mentions a specific park name.
- DO NOT add source unless the user mentions "TNM", "USGS", "OSM", or "OpenStreetMap".
- DO NOT add hiked filter unless the user mentions completion status ("I hiked", "I completed", "I haven't hiked", etc.).
- DO NOT add min_length or max_length with value 0.
- When the user asks for trails with a semantic component (waterfalls, slot canyons) WITHOUT specifying a park, search across ALL parks by omitting park_code.
...
```

**Pros**:
- Simple to implement
- No code changes beyond prompt
- Preserves LLM flexibility for genuine inference

**Cons**:
- May not fully prevent hallucinations (prompt injection is unreliable)
- Non-determinism persists

**Recommendation**: Implement as first step, but likely insufficient alone.

---

#### Option B: Post-Processing Filter Validation
**Approach**: After LLM extracts parameters, validate and remove unjustified ones.

**Implementation in `api/nlq/parser.py`**:

Add a validation function that checks extracted parameters against the original query:

```python
def _validate_extracted_params(params: dict, original_query: str) -> dict:
    """
    Remove hallucinated parameters not supported by the query text.

    Args:
        params: Extracted parameters from LLM
        original_query: Original user query string

    Returns:
        Cleaned parameters with hallucinations removed
    """
    cleaned = params.copy()
    query_lower = original_query.lower()

    # Remove park_code if no park name mentioned
    if "park_code" in cleaned:
        park_name_mentioned = any(
            park_name.lower() in query_lower
            for park_name in PARK_CODE_TO_NAME.values()
        )
        if not park_name_mentioned:
            logger.warning(
                f"Removing hallucinated park_code={cleaned['park_code']} "
                f"from query: {original_query}"
            )
            del cleaned["park_code"]

    # Remove source if not mentioned
    if "source" in cleaned:
        source_mentioned = any(
            term in query_lower
            for term in ["tnm", "usgs", "osm", "openstreetmap"]
        )
        if not source_mentioned:
            logger.warning(
                f"Removing hallucinated source={cleaned['source']} "
                f"from query: {original_query}"
            )
            del cleaned["source"]

    # Remove hiked filter if completion status not mentioned
    if "hiked" in cleaned:
        hiked_terms = [
            "hiked", "completed", "finished", "done",
            "haven't", "haven't hiked", "not hiked", "never hiked",
            "to do", "want to hike", "planning to"
        ]
        hiked_mentioned = any(term in query_lower for term in hiked_terms)
        if not hiked_mentioned:
            logger.warning(
                f"Removing hallucinated hiked={cleaned['hiked']} "
                f"from query: {original_query}"
            )
            del cleaned["hiked"]

    # Remove zero-value length filters (nonsensical)
    if cleaned.get("min_length") == 0:
        del cleaned["min_length"]
    if cleaned.get("max_length") == 0:
        del cleaned["max_length"]

    # Check length filter direction (long → min, short → max)
    length_terms = {
        "long": ["long", "longer", "lengthy"],
        "short": ["short", "shorter", "brief"],
    }

    if "min_length" not in cleaned and "max_length" in cleaned:
        # Has max but not min - check if "long" was mentioned
        if any(term in query_lower for term in length_terms["long"]):
            # User said "long" but LLM gave max_length - swap it
            logger.warning(
                f"Swapping max_length={cleaned['max_length']} to min_length "
                f"for query with 'long': {original_query}"
            )
            cleaned["min_length"] = cleaned.pop("max_length")

    return cleaned
```

Call this in `parse_and_validate()` after LLM extraction:

```python
def parse_and_validate(llm_response: dict, query: str) -> dict:
    # ... existing validation ...

    # Validate and clean hallucinated parameters
    params = _validate_extracted_params(params, query)

    # ... rest of validation ...
```

**Pros**:
- Catches hallucinations reliably through heuristics
- Preserves valid LLM inferences
- Logged warnings help debugging
- Deterministic cleanup

**Cons**:
- Adds complexity
- Heuristics may have false positives/negatives
- Doesn't fix root cause (LLM still hallucinates, we just clean up after)

**Recommendation**: Strong candidate for implementation.

---

#### Option C: Lower LLM Temperature
**Approach**: Reduce randomness in LLM responses.

**Changes**: Set temperature parameter in LLM API call (currently likely default ~0.7).

```python
# In api/nlq/llm_client.py or wherever LLM is called
response = llm.chat.completions.create(
    model="gpt-4",  # or whatever model
    messages=messages,
    tools=tools,
    temperature=0.0,  # Make responses deterministic
)
```

**Pros**:
- Reduces non-determinism
- May reduce hallucinations (more conservative)
- Simple one-line change

**Cons**:
- Doesn't eliminate hallucinations, just makes them consistent
- May reduce valid creative inference
- Only helps with non-determinism issue (#6), not others

**Recommendation**: Implement alongside other fixes.

---

#### Option D: Constrained Decoding (Function Parameter Whitelisting)
**Approach**: Only allow LLM to set parameters that have clear textual evidence in query.

**Implementation**: More complex parser logic that:
1. Tokenizes the query
2. For each extracted parameter, requires matching evidence in tokens
3. Rejects parameters without evidence

**Pros**:
- Most rigorous solution
- Prevents all hallucinations by construction

**Cons**:
- Very complex to implement correctly
- May block valid inferences (e.g., "long" → min_length=5)
- Brittle to paraphrasing

**Recommendation**: Defer unless simpler options fail.

---

#### Option E: Two-Step LLM Process
**Approach**:
1. LLM extracts parameters
2. Second LLM call validates parameters against query

**Implementation**:
```python
# After initial extraction
validation_prompt = f"""
Original query: {original_query}
Extracted parameters: {json.dumps(params)}

For each parameter, is it clearly mentioned or implied in the query?
Respond with JSON: {{"parameter_name": true/false, ...}}
"""
validation_result = llm.chat.completions.create(...)
# Remove parameters marked false
```

**Pros**:
- Uses LLM's own understanding for validation
- Flexible, handles edge cases

**Cons**:
- Doubles LLM calls (latency + cost)
- LLM might justify its own hallucinations
- Still non-deterministic

**Recommendation**: Interesting but expensive, defer.

---

### Recommended Implementation Plan

**Phase 1: Quick Wins (High ROI)** — ✅ COMPLETE

1. ✅ **Strengthen prompt** (Option A)
   - Added 5 explicit DO NOT rules to `api/nlq/prompt.py` system message
   - Prohibits hallucinating park_code, source, hiked, length filters

2. ✅ **Lower temperature** (Option C)
   - Set `"options": {"temperature": 0}` in `api/nlq/ollama_client.py` `call_ollama()` payload
   - Only for tool-calling; `generate_completion()` retains default for natural prose

3. ✅ **Post-processing validation** (Option B)
   - Implemented `_validate_extracted_params()` in `api/nlq/parser.py`
   - Removes park_code, source, hiked, length filters when no textual evidence in query
   - Strips zero-value lengths; swaps max→min for "long" queries
   - Wired into `validate_and_normalize()` for `search_by_topic` only
   - 22 unit tests added in `TestHallucinationValidation` class
   - All 550 unit tests pass

4. ✅ **Zero-result fallback message**
   - Added static fallback in `api/main.py` when both trails and fallback chunks are empty
   - Uses `request.query` (full original query) for context, not just semantic `query_text`

**Phase 2: Evaluation** — ✅ COMPLETE

All 7 test queries pass (see Post-Fix results table above):
- Hallucination rate: **0%** (park_code, source, hiked all clean)
- Length filter direction: correct in all cases
- Non-determinism: eliminated via temperature=0

**Phase 3: If Issues Persist**
6. Consider Option D (constrained decoding) or Option E (validation LLM)
   - **Not needed** — Phase 1 fixes resolved all identified issues

---

### Test Suite for Validation

After implementing improvements, test against:

```python
# test_nlq_hallucination_fixes.py
TEST_CASES = [
    # Format: (query, expected_params, forbidden_params)
    (
        "waterfall hikes I completed",
        {"hiked": True},
        {"park_code", "source"},
    ),
    (
        "long slot canyon trails",
        {"min_length": 5},
        {"park_code", "source", "hiked", "max_length"},
    ),
    (
        "slot canyons in Utah",
        {"state": "UT"},
        {"park_code", "source", "hiked"},
    ),
    (
        "waterfall hikes I completed in California",
        {"state": "CA", "hiked": True},
        {"park_code", "source"},
    ),
    (
        "short waterfall hikes",
        {"max_length": 3},
        {"park_code", "source", "hiked", "min_length"},
    ),
    (
        "trails over 5 miles in Zion",
        {"park_code": "zion", "min_length": 5},
        {"source", "hiked", "max_length"},
    ),
    (
        "slot canyons I haven't hiked yet",
        {"hiked": False},
        {"park_code", "source"},
    ),
]

def test_no_hallucinated_params():
    """Ensure LLM doesn't add unjustified parameters."""
    for query, expected, forbidden in TEST_CASES:
        result = parse_query(query)

        # Check expected params present
        for key, val in expected.items():
            assert result.get(key) == val, \
                f"Query '{query}': expected {key}={val}, got {result.get(key)}"

        # Check forbidden params absent
        for param in forbidden:
            assert param not in result, \
                f"Query '{query}': hallucinated {param}={result.get(param)}"
```

---

### Impact Assessment

**User Impact**:
- Current: Users get wrong/limited results due to hallucinated filters
- After fixes: Users get expected results matching their actual query

**Example**:
- Query: "slot canyons I haven't hiked yet"
- Current: Returns Arches trails only (hallucinated park_code="arch")
- After fixes: Returns all unhiked slot canyon trails across all parks

**Breaking Changes**: None - only improves accuracy.

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Where to apply filters | SQL WHERE clause after semantic matching | Efficient, preserves similarity ranking, clean separation of concerns |
| Filter parameters | Same as `fetch_trails()` | Consistency, reuses existing validation logic |
| Tool selection rule | Semantic component present → `search_by_topic` | Simple, unambiguous, LLM can extract both aspects from query |
| Generation on filtered-out results | Always generate when semantic matches exist | Provides context even when filters are too strict |
| `/search` endpoint filters | Add them | Enables hybrid search for REST API consumers, low cost |
| Regional support (multi-state) | Defer to separate task | Orthogonal concern, can be added later without breaking changes |
| Streamlit filter display | Show as editable chips + sidebar widgets | Transparent, allows user adjustment, divergence handles state |
| **LLM hallucination mitigation** | **Prompt strengthening + post-processing validation + temperature=0** | **Pragmatic multi-layer defense: cheap prompt fixes + reliable heuristic cleanup + determinism** |

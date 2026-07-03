# Streamlit Webapp Plan: NPS Hikes Interactive Map

> **Status Update (2026-04-12):** Phase 4 in progress. Park pin UX redesigned: hover→tooltip (name + visit info), click→select park. Popups removed from park markers. NPS descriptions moved to sidebar summary. Home button on map. Sidebar reordered: Select Parks → Park Summary → Filter Trails. Boundary tooltip now only shows on the border line, not inside the polygon. See [Phase 4 Progress](#phase-4-progress-2026-04-12) below for details.

## Objective

Build a Streamlit web application that provides an interactive map interface for exploring National Park hiking trails. The app will demonstrate **dual-mode interaction**: users can filter trails using traditional GUI controls (dropdowns, sliders, toggles) OR use natural language queries, with both modes converging on the same unified map view.

---

## Implementation Status

> **Latest Update (2026-04-12):** Phase 4 UX polish round 2. Park pin interaction redesigned: hover shows tooltip with park name + visit info, click immediately selects park (no popup). NPS descriptions accessible in sidebar summary expander. Home button added to map. Sidebar section order updated. Boundary polygon tooltip now only appears on the border line (split into fill + line layers). All 444 unit tests pass, lint clean. See [Phase 4 Progress](#phase-4-progress-2026-04-12) below.

### ✅ Phase 1 (MVP) - COMPLETE

**Location:** `streamlit_app/` directory at project root

**What's Working:**
- ✅ Interactive Folium map with multiple layers:
  - Park center markers (green=visited, gray=unvisited)
  - Park boundary polygons (blue outline)
  - Trail LineStrings (green=hiked solid, gray=not hiked dashed)
  - Hiking location markers from Google My Maps (orange dots)
  - Tooltips and popups on all map elements
- ✅ Sidebar with filters and controls:
  - State filter (correctly parses multi-state parks like "CA,NV")
  - Visit status filter (visited/not visited)
  - Park multi-select with "Clear All" button
  - **Trail name search** (client-side filtering, case-insensitive)
  - Trail filters: hiked status, length range (slider), data source (TNM/OSM), 3D viz availability
  - Expandable park summary cards
- ✅ Data table component:
  - Sortable trail list with columns: Trail, Park, Length, Source, Hiked, 3D Viz
  - Clickable 3D visualization links
  - Summary metrics (total miles, hiked count, 3D viz count)
  - **Export buttons** for CSV and GeoJSON downloads
- ✅ API integration:
  - HTTP client with caching (5 min for parks/stats, 1 min for trails)
  - Configurable endpoint via `NPS_API_URL` env var (defaults to `localhost:8001`)
  - Error handling for API failures
- ✅ Session state management for selected parks and cached data
- ✅ Comprehensive README with setup instructions

**Known Issues:**
- ✅ **"Clear All" button fixed** (2026-04-06) - Now uses `on_click` callback pattern
- ⚠️ State filtering - Code fixed for multi-state parks, needs user testing
- ⚠️ All widgets have unique keys - Fixed, needs verification
- ⚠️ Sidebar renders once per cycle - Fixed, needs verification
- ⚠️ Trail filters - Should work, needs testing
- ⚠️ Data table - Should display correctly, needs testing
- 🆕 **Selected park summary appears flaky** - Sometimes doesn't render, especially with multiple parks (see User Feedback below)

**What's NOT Implemented Yet:**
- Trail highlighting on table row click (planned for Phase 4)
- Map marker click to select parks (currently manual selection only)

### 📋 Next Steps

**Priority: UX Polish Pass (from User Feedback 2026-04-06)** — ✅ ALL DONE
1. ✅ **Header stats removed entirely** — title now sits directly above the map. Reactive Parks/States/Hiked/3D-Viz counts moved to the metrics row beneath the trail table.
2. ✅ **Selected Parks Summary fixed** — root cause was a one-rerun-lag bug: summaries were fetched against `st.session_state.selected_parks` (the *previous* run's value), but the multiselect widget's new value isn't committed there until after the sidebar renders. Fix: read directly from `st.session_state.get("park_multiselect", ...)` so the fetch sees the current selection on the same rerun. Also wrapped in `st.spinner()`, switched to `ThreadPoolExecutor` for parallel fetches, and surfaced fetch errors as `st.warning(...)` in the sidebar instead of swallowing them.
3. ✅ **Reset Filters button added** to the Filter Trails section using the same `on_click` callback pattern as Clear All ([sidebar.py:26-37](streamlit_app/components/sidebar.py#L26-L37)).
4. ✅ **Emoji removed** from the main title.

**Resolved (2026-04-06): Requirements file location**
- ✅ Moved to `streamlit_app/requirements.in` and `streamlit_app/requirements.txt`.
- Rationale: the streamlit app is treated as a separate deployable unit (it only imports `streamlit_app.*`, not `api.*`), so its dependencies live with it. Mirrors the monorepo convention of "each deployable has its own dependency manifest in its own directory."
- Install from project root: `pip install -r streamlit_app/requirements.txt`.
- Recompile from project root: `pip-compile streamlit_app/requirements.in`.

**Phase 3 (NLQ Integration) — COMPLETE:**
- ✅ NLQ chat input in sidebar (`st.chat_input` with send icon, replaces old form + "Ask" button)
- ✅ Interpreted parameter chips display (with ✕ dismiss button)
- ✅ Auto-set GUI widgets from NLQ results (all four tools handled)
- ✅ Error handling for Ollama unavailability (503, 422, 429, 404)
- ✅ Divergence detection — chips shift from green-tinted to grey when filters change after NLQ query; caption updates with ⚠️
- ✅ Stats card rendering for `search_stats` tool (above the map)
- ✅ API retry logic — if LLM returns plain text instead of a tool call, the API nudges it once to use a function call before failing
- ✅ Unit tests passing (359 total); `ruff check` and `ruff format` clean

**Phase 4 (Not Started):**
- 🔲 Trail highlighting on table click
- 🔲 Shareable URLs with encoded filters
- 🔲 Map marker click for park selection

---

## User Feedback (2026-04-06)

After working session testing, the user provided the following UX feedback:

### 1. Header Stats Take Too Much Space and Are Not Reactive

**Problem:** The 4 metric columns under the title (`Total Trails`, `Total Miles`, `Parks`, `States`) consume significant vertical space above the map and never change based on user selections.

**Suggested Fix:**
- Move `Parks` count and `States` count out of the header
- Reposition them next to or above the trail data table where they can be reactive to filters
- The reactive table area should show counts based on currently selected parks and active filters
- Consider a more compact header layout with just `Total Trails` / `Total Miles`, OR move all stats to be reactive at the bottom

**Files Likely Affected:** [app.py](streamlit_app/app.py) (header section ~L97-L106), [data_table.py](streamlit_app/components/data_table.py)

---

### 2. Selected Parks Summary in Sidebar Is Flaky

**Problem:** The "Selected Parks Summary" expandable cards in the sidebar sometimes don't appear, particularly when multiple parks are selected. It's unclear whether a slow computation is happening or if the fetch is failing silently.

**Hypotheses:**
- `fetch_park_summary()` may be blocking and slow when called sequentially for multiple parks
- API errors are silently swallowed (`pass` in the except block) so failures aren't visible
- The summary cards may render but appear out of view if the sidebar is long

**Suggested Fix:**
- Wrap the multi-park summary fetch in `st.spinner("Loading park summaries...")` so users see feedback
- Surface API errors instead of silently passing — log to console or show a small warning icon
- Consider parallel fetching of summaries (e.g., `concurrent.futures.ThreadPoolExecutor`) since each is an independent HTTP call
- Investigate whether the issue is reproducible by selecting 3+ parks at once

**Files Likely Affected:** [app.py:108-116](streamlit_app/app.py#L108-L116) (summary fetch loop), [sidebar.py:171-196](streamlit_app/components/sidebar.py#L171-L196) (summary rendering)

---

### 3. Add Reset Button to Filter Trails Section

**Problem:** The Park Selection section has a "Clear All" button, but the "Filter Trails" section has no equivalent way to reset all trail filters at once.

**Suggested Fix:**
- Add a "Reset Filters" button at the top or bottom of the Filter Trails section
- Should reset: trail name search, hiked status (back to "All Trails"), length slider (back to 0-20), source (back to "All Sources"), 3D viz (back to "All Trails")
- **IMPORTANT:** Use the same `on_click` callback pattern as `_clear_park_selection()` to avoid `StreamlitAPIException` about modifying widget state after instantiation
- Each widget's session state key needs to be reset in the callback:
  - `filter_trail_name_input` → `""`
  - `filter_hiked_radio` → `"All Trails"`
  - `filter_length_slider` → `(0.0, 20.0)`
  - `filter_source_select` → `"All Sources"`
  - `filter_viz_3d_radio` → `"All Trails"`

**Files Likely Affected:** [sidebar.py](streamlit_app/components/sidebar.py)

---

### 4. Requirements File Location — RESOLVED

**Decision (2026-04-06):** Moved into `streamlit_app/` and renamed to drop the now-redundant `-streamlit` suffix:
- `requirements-streamlit.in` → `streamlit_app/requirements.in`
- `requirements-streamlit.txt` → `streamlit_app/requirements.txt`

**Rationale:** the streamlit app is treated as a separate deployable unit that consumes the FastAPI backend over HTTP. It only imports `streamlit_app.*` — never `api.*` or shared internal modules — so it's logically self-contained. Per typical monorepo conventions, each deployable owns its own dependency manifest in its own directory. Install with `pip install -r streamlit_app/requirements.txt` from the project root.

---

### 5. Remove Emoji from Main Title

**Problem:** The main panel title `🏞️ NPS Hikes Interactive Explorer` has an emoji that may feel out of place for a professional tool.

**Fix:** Remove the `🏞️` emoji from `st.title()` call.

**Location:** [app.py:97](streamlit_app/app.py#L97)

**Note:** Sidebar title `🏞️ NPS Hikes Explorer` can keep its emoji (less prominent context).

---

## Running the App

```bash
# 1. Activate virtualenv
source ~/.virtualenvs/nps-hikes/bin/activate

# 2. Install dependencies
pip install -r streamlit_app/requirements.txt

# 3. Start the database container
docker compose up db -d

# 4. Start the API locally (connects to Docker DB, serves on :8001)
make dev

# 5. In another terminal, run Streamlit (connects to API on :8001)
make streamlit
```

The app will open at http://localhost:8501.

### Development workflow notes

**`make dev`** runs the API locally with `POSTGRES_HOST=localhost POSTGRES_PORT=5433 --port 8001`. This connects to the Docker database (exposed on host port 5433) and serves the API on port 8001 — the same port the Streamlit client defaults to. Running the API locally (not in Docker) also means it can reach Ollama on the host machine for NLQ queries.

**`make up`** runs both the database and API in Docker containers. The Docker API is exposed on port 8000 (not 8001), and cannot reach Ollama on the host. Use `make up` for non-NLQ workflows, or set `NPS_API_URL=http://localhost:8000 make streamlit`.

---

## Core Design Principles

1. **API-driven architecture** — Streamlit is a pure HTTP client calling the FastAPI backend. No direct database access. All data flows through the REST API.

2. **Unified view with dual input modes** — GUI filters and NLQ queries both update the same map + data table. Not separate tabs or split views.

3. **NLQ sets GUI state ("unified + chips")** — When a user asks "long trails I haven't hiked in Utah", the NLQ endpoint returns `interpreted_as: {state: "UT", hiked: false, min_length: 5}`. The Streamlit app:
   - Shows these params as visual "chips" so the user sees what the LLM understood
   - Auto-sets the GUI widgets to match (state dropdown → UT, hiked toggle → false, length slider → 5+)
   - Re-runs the normal data-fetching code with those widget values
   - Result: NLQ and GUI are always in sync. User can tweak the NLQ's interpretation by adjusting the GUI controls.

4. **Layer-based map** — Users toggle parks on/off as map layers. Each park shows:
   - Simplified boundary polygon (outline)
   - Trail LineStrings (colored green=hiked, gray=not hiked)
   - GMaps hiking location markers (small dots on hiked trails)
   - Park center marker (clickable for park description)

5. **Progressive disclosure** — Start simple (national view with park dots), layer in complexity as user drills down (select park → see boundary + trails + markers).

---

## User Experience Walkthrough

### On App Load

**What the user sees:**
- Header with aggregate stats (e.g., "347 trails across 36 parks, 1,523 total miles")
- A map centered on the continental US showing 63 park markers (dots)
- Sidebar with filter controls (all in default/empty state)
- Empty data table below the map

**API calls on load:**
- `GET /parks` → all 63 parks (names, lat/lon, states, visit info) — ~10 KB
- `GET /stats` → aggregate totals (trails, miles, parks) — ~1 KB

**Map state:** Shows US with park markers. Visited parks in one color, unvisited in another. No boundaries or trails yet.

---

### Filter by State (GUI)

**User action:** Selects "CA" from state multi-select dropdown in sidebar.

**What happens:**
- Client-side filter: dim/hide non-CA park markers on the map
- Park dropdown narrows to show only CA parks (e.g., Yosemite, Sequoia, Death Valley, etc.)
- Stats update to show CA-only counts

**No new API calls** — filtering happens client-side using the already-loaded park data.

---

### Select a Park (GUI)

**User action:** Selects "Yosemite" from park dropdown OR clicks the Yosemite marker on the map.

**What happens:**
Three API calls in parallel:
1. `GET /parks?park_code=yose&boundary=true` → simplified boundary GeoJSON polygon (~9 KB)
2. `GET /trails?park_code=yose&geojson=true&limit=1000` → ~40 trails with LineString geometries (~400 KB)
3. `GET /trails/hiked-points?park_code=yose` → GMaps marker points for Yosemite (~5 KB)

**Map updates:**
- Zooms to Yosemite bounding box
- Draws park boundary as a polygon outline (light blue)
- Draws trails as lines: green (hiked), gray (not hiked)
- Plots GMaps markers as small colored dots
- Park center marker stays visible (clickable); on click, user can read park name and expand to see description.

**Sidebar updates:**
- Park summary card appears showing:
  - Total trails: 42
  - Total miles: 187.3
  - Hiked trails: 15 (67.2 miles)
  - 3D viz available: 10 trails

**Below map:**
- Data table populates with 42 trail rows (name, length, source, hiked, 3D viz link)
- Sortable by any column
- Click a trail name → highlights that trail on the map

---

### Apply Trail Filters (GUI)

**User action:** Sets filters in sidebar:
- Hiked: "Not Hiked" (false)
- Min length: 5 miles
- Trail type: "Path"

**What happens:**
- New API call: `GET /trails?park_code=yose&hiked=false&min_length=5&geojson=true&limit=1000`
- Map updates to show only trails matching filters (e.g., 8 trails remain)
- Data table updates to show only matching trails
- Park boundary and GMaps markers remain visible (unchanged)

**Sidebar stats update:** "Showing 8 of 42 trails (42.3 miles)"

---

### Toggle Multiple Parks (GUI)

**User action:** Clicks "Add Park" and selects "Zion" from dropdown.

**What happens:**
- Same 3 API calls for Zion:
  1. `GET /parks?park_code=zion&boundary=true`
  2. `GET /trails?park_code=zion&geojson=true&limit=1000`
  3. `GET /trails/hiked-points?park_code=zion`
- Map now shows BOTH Yosemite and Zion layers simultaneously
- Data table merges trails from both parks (sorted by park then name)
- Sidebar shows summary stats for both parks

**Map zoom:** Adjusts to fit both parks' bounding boxes.

**Note:** Filters apply across all selected parks (e.g., "hiked=false" shows unhiked trails from both Yosemite AND Zion).

---

### Natural Language Query

**User action:** Types in NLQ input box: "Show me long trails I haven't hiked in Utah"

**What happens:**

1. **API call:** `POST /query` with body `{"query": "Show me long trails I haven't hiked in Utah"}`

2. **Response:**
```json
{
  "original_query": "Show me long trails I haven't hiked in Utah",
  "interpreted_as": {
    "state": "UT",
    "hiked": false,
    "min_length": 5
  },
  "function_called": "search_trails",
  "results": { ... }  // Ignored by Streamlit
}
```

3. **Streamlit updates GUI state:**
   - Display "interpreted as" chips above the map: `[State: UT] [Hiked: No] [Min Length: 5 mi]`
   - Auto-set sidebar widgets:
     - State multi-select → UT
     - Hiked toggle → "Not Hiked"
     - Min length slider → 5
   - Normal data-fetching code re-runs with these widget values
   - Fetches `GET /trails?state=UT&hiked=false&min_length=5&geojson=true&limit=1000`

4. **Map updates:** Shows all Utah parks with trails matching the filters.

5. **User can refine:** User sees the chips, realizes they wanted 10+ miles, adjusts slider to 10. Map updates. NLQ and GUI stay synchronized.

---

## Sidebar Layout (Proposed)

```
┌─────────────────────────────────┐
│ 🏞️ NPS Hikes Explorer          │
├─────────────────────────────────┤
│ Natural Language Query          │
│ ┌─────────────────────────────┐ │
│ │ "Show me trails in Yosemite"│ │
│ └─────────────────────────────┘ │
│ [Submit]                        │
│                                 │
│ Interpreted as:                 │
│ [Park: Yosemite] [×]           │
│                                 │
├─────────────────────────────────┤
│ Filter by Location              │
│ ┌─────────────────────────────┐ │
│ │ State: [▼ CA, UT, WY ...]   │ │
│ └─────────────────────────────┘ │
│ ┌─────────────────────────────┐ │
│ │ Park: [▼ Select park(s)...] │ │
│ └─────────────────────────────┘ │
│ ☑ Only visited parks            │
│                                 │
├─────────────────────────────────┤
│ Filter Trails                   │
│ Hiked: ( ) All (•) Yes ( ) No  │
│                                 │
│ Trail Length (miles)            │
│ [====|========] 0 - 20+         │
│                                 │
│ Source: ( ) All ( ) TNM ( ) OSM│
│                                 │
│ [Trail type filter removed]     │
│                                 │
│ ☑ Only trails with 3D viz       │
│                                 │
├─────────────────────────────────┤
│ Selected Park Summary           │
│ 📍 Yosemite National Park       │
│ • 42 trails (187.3 mi)          │
│ • 15 hiked (67.2 mi)            │
│ • 10 with 3D visualization      │
│ [View Park Details]             │
└─────────────────────────────────┘
```

---

## Main Area Layout

```
┌──────────────────────────────────────────────────┐
│ 347 trails | 36 parks | 1,523 total miles        │ ← Header stats
├──────────────────────────────────────────────────┤
│                                                  │
│                                                  │
│                  MAP AREA                        │ ← Leaflet/Folium map
│         (Interactive, zoomable)                  │
│                                                  │
│                                                  │
└──────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────┐
│ Trail | Park | Length | Source | Hiked | 3D     │ ← Data table
├───────┼──────┼────────┼────────┼───────┼────────┤
│ Half  │ Yose │ 14.2   │ TNM    │  ✓    │ [View] │
│ Dome  │      │        │        │       │        │
├───────┼──────┼────────┼────────┼───────┼────────┤
│ Mist  │ Yose │  6.3   │ OSM    │  ✗    │   —    │
│ Trail │      │        │        │       │        │
└───────┴──────┴────────┴────────┴───────┴────────┘
```

---

## Map Layers & Styling

### Layer 1: Park Center Markers
- **Data source:** `GET /parks` (lat/lon)
- **Styling:**
  - Visited: green circle marker
  - Unvisited: gray circle marker
- **Interaction:** Click → popup with park name, description, visit date
- **Always visible** (even when park boundary layer is active)

### Layer 2: Park Boundaries
- **Data source:** `GET /parks?park_code={code}&boundary=true` (simplified GeoJSON polygon)
- **Rendered as two sub-layers** so the tooltip only appears on the boundary line:
  - Fill layer: semi-transparent light blue (20% opacity), transparent stroke, no tooltip
  - Line layer: exterior ring(s) extracted as LineString/MultiLineString, solid blue 2px, tooltip on hover
- **Loaded on-demand** when park is selected
- **Multiple parks can be shown simultaneously**

### Layer 3: Trail Lines
- **Data source:** `GET /trails?park_code={code}&geojson=true` (LineString GeoJSON)
- **Styling:**
  - Hiked trails: solid green, 3px width
  - Not-hiked trails: dashed gray, 2px width
  - Highlighted trail (on table row click): yellow, 5px width
- **Tooltip on hover:** Trail name, length
- **Click:** Highlight in table, show trail details panel

### Layer 4: GMaps Hiking Markers
- **Data source:** `GET /trails/hiked-points?park_code={code}`
- **Styling:**
  - Small red/orange circle markers (distinct from park markers)
  - Slightly transparent (70% opacity)
- **Tooltip:** Location name, matched trail (if any)
- **Only shown for hiked trails**

---

## NLQ Integration Details

### NLQ Workflow

1. User types query, clicks Submit
2. Streamlit calls `POST /query`
3. Receives `interpreted_as` dict (e.g., `{state: "CA", hiked: true, min_length: 10}`)
4. **Ignore the `results` field** — we'll re-fetch with `geojson=true`
5. Display chips showing interpreted params
6. Set `st.session_state` for each widget to match the interpreted params
7. Streamlit re-runs, widgets reflect new state
8. Normal data-fetching code executes with `geojson=true` added
9. Map updates

### Handling NLQ Edge Cases

- **LLM misinterprets query:** User sees the chips, realizes the mistake, adjusts GUI manually
- **Ambiguous park name:** LLM may fail. Show error chip: "Could not identify park 'Yellowstone' — did you mean 'yell'?" with suggestion
- **No results:** Show message: "No trails match these filters. Try adjusting?"
- **Ollama unavailable (503):** Show error: "Natural language search is currently unavailable. Use filters instead."

### Example NLQ Queries

| Query | Interpreted As | Result |
|---|---|---|
| "Show me trails in Yosemite" | `{park_code: "yose"}` | Selects Yosemite, loads all trails |
| "Long hikes in California" | `{state: "CA", min_length: 10}` | CA parks, trails ≥10 mi |
| "What have I hiked in Utah?" | `{state: "UT", hiked: true}` | UT parks, hiked trails only |
| "Short easy trails I haven't done" | `{hiked: false, max_length: 3}` | All parks, ≤3 mi unhiked |
| "Tell me about Zion" | `{park_code: "zion"}` via `search_park_summary` | Shows park summary card |
| "How many miles have I hiked?" | `{hiked: true}` via `search_stats` | Shows aggregate stats modal |

---

## Tech Stack

### Recommended: Streamlit + Leaflet

- **Streamlit** — Python-based web framework, ideal for rapid prototyping
- **Folium** or **streamlit-folium** — Leaflet.js integration for interactive maps
- **Requests** — HTTP client for API calls
- **Pandas** (optional) — for data table manipulation

### Alternative: Streamlit + Plotly

- **Plotly Express** — `px.scatter_map()` for simple marker maps
- **Downside:** Less control over multi-layer maps compared to Leaflet

### Not Recommended for Prototype:
- React + Vite — too much overhead for a prototype
- HTMX — limited interactivity for map-heavy UX

---

## Data Flow Summary

```
┌──────────────┐
│  Streamlit   │
│     App      │
└──────┬───────┘
       │
       ├─ On load ────────────────┐
       │                          ▼
       │                  GET /parks (all 63)
       │                  GET /stats
       │
       ├─ Select park ────────────┐
       │                          ▼
       │                  GET /parks?park_code=yose&boundary=true
       │                  GET /trails?park_code=yose&geojson=true&limit=1000
       │                  GET /trails/hiked-points?park_code=yose
       │
       ├─ Apply filter ───────────┐
       │                          ▼
       │                  GET /trails?park_code=yose&hiked=false&min_length=5&geojson=true
       │
       ├─ NLQ query ──────────────┐
       │                          ▼
       │                  POST /query {"query": "..."}
       │                          │
       │                          ▼
       │                  Parse interpreted_as
       │                  Set GUI widget state
       │                  Re-fetch with geojson=true
       │
       └─ Click park marker ──────┐
                                  ▼
                          GET /parks?park_code=yose&description=true
                          (for popup content)
```

---

## Performance Considerations

### Data Size Estimates (per park)
- Park boundary: ~9 KB (simplified)
- 40 trails with geometry: ~400 KB
- GMaps markers: ~5 KB
- **Total per park: ~415 KB**

For 3 parks simultaneously: ~1.2 MB. Acceptable for modern web browsers.

### Optimization Strategies
1. **Lazy loading** — Only fetch boundary + trails when park is selected, not on initial load
2. **Client-side caching** — Cache park boundaries in `st.session_state`, don't re-fetch if already loaded
3. **Debounced filters** — Don't re-fetch on every slider drag; wait for user to release
4. **Pagination** (future) — If showing 100+ trails, use the API's pagination (`limit`, `offset`)

---

## Phased Rollout Plan

### Phase 1: Minimal Viable Map (MVP) ✅ COMPLETE

**Status:** ✅ **DONE** (2026-04-04)

**Features Implemented:**
- ✅ Map with park markers (visited=green, unvisited=gray)
- ✅ Sidebar: state filter (handles multi-state parks), visit status filter, park multi-select
- ✅ Select park → load boundary + trails + GMaps markers (all three working!)
- ✅ Data table below map (sortable, with 3D viz links)
- ✅ Trail filters: hiked status, length slider, source filter, 3D viz filter
- ✅ Park summary cards in sidebar (expandable)
- ✅ Stats header with total trails, miles, parks, states

**Extras Beyond Original Phase 1 Plan:**
- ✅ GMaps hiking markers already implemented (originally planned for Phase 4)
- ✅ Park summary cards already implemented (originally planned for Phase 4)
- ✅ Stats header already implemented (originally planned for Phase 4)
- ✅ Multi-park selection working (originally planned for Phase 4)

**Success criteria:** ✅ PASSED - User can select Yosemite, see trails on map, filter by hiked status, view multiple parks, see GMaps markers.

**Known Issues to Fix:**
- Need user testing on state filter with multi-state parks
- Need testing on multiple park selection (UI shows correctly but needs verification)
- Trail highlighting on table click not yet implemented

---

### Phase 2: Enhanced Trail Filters ✅ MOSTLY COMPLETE

**Status:** ✅ **MOSTLY DONE** (2026-04-04)

**Completed Features:**
- ✅ Hiked toggle (radio: All/Hiked/Not Hiked)
- ✅ Length slider (min/max 0-20 miles)
- ✅ Source filter (TNM/OSM)
- ✅ 3D viz filter (radio: All/With/Without)
- ✅ **Trail name search box** (client-side filtering, case-insensitive)
- ✅ **Export trails to CSV/GeoJSON** (download buttons above table)

**Removed:**
- ❌ Trail type dropdown (removed per user feedback - not interesting)

**Still TODO for Phase 2 (optional enhancements):**
- 🔲 Filter presets (save/load common filter combinations)
- 🔲 Advanced search (regex, full-text)

**Success criteria:** ✅ PASSED - User can search trails by name and export filtered results to CSV/GeoJSON.

---

### Phase 3: NLQ Integration ✅ COMPLETE

**Status:** ✅ **COMPLETE** (2026-04-11)

#### Phase 3 Progress (2026-04-11)

**What's been built:**

1. **`components/nlq.py`** (~600 lines) — full NLQ module containing:
   - `render_nlq_form()` — `st.chat_input` with built-in send icon at the top of the sidebar (replaced original `st.form` + "Ask" button)
   - `process_pending_nlq_query()` — two-rerun pending-flag pattern: chat input submit sets `nlq_pending` + `st.rerun()` → top of `main()` shows `st.spinner`, calls `POST /query`, routes response to translation layer → `st.rerun()` → widgets pick up new state
   - `_apply_trail_search_params()` — translates `search_trails` params to widget state (park_code, state, hiked, length slider, source); auto-relaxes `filter_state_select` and `filter_visited_radio` when a park_code is set so the park is visible in multiselect options
   - `_apply_park_summary_params()` — translates `search_park_summary` to park multiselect + relaxes state/visited
   - `_apply_park_filter_params()` — translates `search_parks` to visited filter only
   - `render_nlq_chips_and_results()` — chip row above the map with color-coded staleness (green=active, grey=stale); for `search_stats`, renders a stats card instead of updating widgets
   - `_nlq_params_diverged()` — compares current widget state to stashed NLQ params; triggers green→grey chip transition + caption update when widgets have been manually changed
   - `_clear_nlq_state()` — callback for ✕ dismiss button on chips

2. **`api/client.py`** modifications:
   - `APIError` now carries a `status_code` attribute for HTTP error differentiation
   - New `post_nlq_query(query)` function — uncached, 60-second timeout, status-code-aware error handling

3. **`components/sidebar.py`** modifications:
   - NLQ chat input rendered at top of sidebar (above "Select Parks") with a divider
   - Removed sidebar title (`🏞️ NPS Hikes Explorer`) — redundant with main panel title
   - Removed `default=` from multiselect and `value=` from length slider to avoid Streamlit warnings when NLQ writes to widget session state; both now driven purely via session state

4. **`app.py`** modifications:
   - Wired in `initialize_nlq_state()`, `process_pending_nlq_query(all_parks)`, and `render_nlq_chips_and_results(all_parks)` at appropriate points in the main flow
   - Added `menu_items` to `st.set_page_config`: "Get help" → GitHub repo, "Report a bug" → GitHub issues, "About" → docs site link

5. **`api/main.py`** modifications:
   - Added retry logic in `/query` endpoint: if `parse_tool_call` fails (LLM returned plain text instead of a tool call), the API appends the failed response + a nudge message and retries Ollama once before raising a 422

6. **`Makefile`** modifications:
   - `make dev` now includes `POSTGRES_HOST=localhost POSTGRES_PORT=5433 --port 8001` so it connects to the Docker DB and serves on the same port the Streamlit client expects

**Design decisions (per user direction):**
- All four NLQ tools handled (`search_trails`, `search_parks`, `search_stats`, `search_park_summary`)
- `st.chat_input` for compact UX (built-in send icon, Enter-to-submit, auto-clear)
- Chips lifecycle: chips persist as historical record; green→grey color shift + ⚠️ caption when filters diverge
- Stats results render as a card above the map rather than mutating widgets
- API retries once on tool-call parse failure to improve LLM reliability

**Verified:**
- ✅ `search_trails` with `{state: "UT", hiked: False, min_length: 5.0}` → `filter_state_select=UT`, `filter_hiked_radio="Not Yet Hiked"`, `filter_length_slider=(5.0, 20.0)`
- ✅ `search_park_summary` for Zion → `park_multiselect=['zion']`, state relaxed to "All States"
- ✅ 503 error → sidebar shows "Natural language search is unavailable. Is Ollama running?"
- ✅ 422 error → sidebar shows "Couldn't interpret that query. Try being more specific…"
- ✅ All 359 unit tests pass; `ruff check` and `ruff format` clean
- ✅ Dev workflow: `docker compose up db -d` + `make dev` + `make streamlit` works end-to-end

**Success criteria:** ✅ PASSED — User types NLQ query, sees colored chips, GUI updates, map shows filtered trails. Chip staleness visually indicated when filters are manually changed.

---

### Phase 4: Polish & Enhancements 🔄 IN PROGRESS

**Status:** 🔄 **CORE FEATURES IMPLEMENTED, NEEDS BROWSER TESTING**

**Already Implemented (moved to Phase 1):**
- ✅ GMaps hiking location markers on map
- ✅ Multi-park selection (toggle multiple parks on map)
- ✅ Park summary card in sidebar
- ✅ Stats header

#### Phase 4 Progress (2026-04-11)

**What was built (initial round):**

1. **Quieter map tiles** ([map.py:52](streamlit_app/components/map.py#L52))
   - ✅ Switched from `"OpenStreetMap"` to `"CartoDB Positron"` — light gray tiles that make trail lines and park boundaries stand out

2. **Teardrop pin markers** ([map.py:86-92](streamlit_app/components/map.py#L86-L92))
   - ✅ Replaced `folium.CircleMarker` with `folium.Marker` + `folium.Icon`
   - Visited parks: green pin (`icon="info-sign"`), Unvisited: light gray pin, Selected: dark green pin (`icon="ok-sign"`)

3. ~~**Park description popups**~~ — **Removed in 2026-04-12 UX redesign** (see below)

4. **Map marker click → park selection** ([app.py:109-118](streamlit_app/app.py#L109-L118), [app.py:278-304](streamlit_app/app.py#L278-L304))
   - ✅ `st_folium` returns `last_object_clicked` (lat/lng); matched to park code via coordinate lookup (switched from tooltip-text matching in 2026-04-12 redesign)
   - ✅ Uses **pending-flag pattern** (like NLQ): map click stashes `pending_park_click` in session state + `st.rerun()` → top of `main()` pops the flag and mutates `park_multiselect` BEFORE the widget is instantiated — avoids `StreamlitAPIException`
   - ✅ Tracks `last_processed_click` (coordinates) to prevent infinite rerun loops
   - ✅ Non-park clicks (trails, boundaries) ignored because coordinates don't match any park lat/lng

5. **Trail row click → highlight + map reposition** ([data_table.py:117-157](streamlit_app/components/data_table.py#L117-L157), [app.py:316-333](streamlit_app/app.py#L316-L333))
   - ✅ `st.dataframe` now uses `on_select="rerun"` with `selection_mode="single-row"` and `key="trail_table"`
   - ✅ Selected row returns full trail dict (with geometry); map center/zoom overridden to trail centroid at zoom 14
   - ✅ Highlighted trail rendered in gold (#FFD700), weight 5, solid line (no dash even if unhiked)
   - ✅ `compute_trail_center()` helper added to [formatting.py:162-193](streamlit_app/utils/formatting.py#L162-L193) — extracts centroid from GeoJSON LineString/MultiLineString
   - ✅ `get_trail_color()` updated to accept `highlighted_trail_id` parameter ([formatting.py:131-147](streamlit_app/utils/formatting.py#L131-L147))
   - ✅ Highlight clears when park selection changes or when no row is selected

#### Phase 4 Progress (2026-04-12)

**UX redesign — park pin hover/click interaction:**

The original popup-based UX had a fundamental flaw: clicking a park pin opened a popup AND immediately selected the park. The `st.rerun()` destroyed the popup before the user could read it. After evaluating several alternatives (two-step confirmation bar below the map, interactive buttons inside the popup, double-click), settled on the simplest approach: **hover for info, click to select**.

**Key constraint:** Folium popups are static HTML inside a Leaflet iframe — they cannot trigger Streamlit state changes (no `on_click` callbacks). This ruled out in-popup interactive buttons.

6. **Park pin tooltip redesign** ([map.py:76-84](streamlit_app/components/map.py#L76-L84))
   - ✅ Replaced `folium.Popup` with `folium.Tooltip` — tooltip shows on hover, disappears on mouseout
   - ✅ Tooltip shows: park full name + visit info line (e.g., `"CA (June 2023)"` or `"WV (Not visited)"`)
   - ✅ Description removed from tooltip — too long for ephemeral hover; moved to sidebar summary
   - ✅ Global CSS override for Leaflet tooltips: `white-space: normal; min-width: 200px; max-width: 350px` — fixes long park names overflowing
   - ✅ New `format_park_visit_line()` helper in [formatting.py:42-63](streamlit_app/utils/formatting.py#L42-L63)

7. **NPS description in sidebar summary** ([sidebar.py:205-211](streamlit_app/components/sidebar.py#L205-L211))
   - ✅ Full park description now shown inside the existing park summary expander, labeled "NPS Description"
   - ✅ Looks up description from `all_parks` (already loaded with `description=True`)

8. **Sidebar section reorder** ([sidebar.py:168-213](streamlit_app/components/sidebar.py#L168-L213))
   - ✅ "Selected Parks Summary" moved from bottom of sidebar to between "Select Parks" and "Filter Trails"
   - ✅ Flow is now: NLQ → Select Parks → Park Summary → Filter Trails (logical progression)

9. **Map home button** ([map.py:32-72](streamlit_app/components/map.py#L32-L72))
   - ✅ Added 🏠 button to top-left map controls (next to zoom +/−)
   - ✅ Clicking resets map to default US overview (center: 39.83°N, 98.58°W, zoom 4)
   - ✅ Implemented via Leaflet `L.Control` extension using Folium's `MacroElement` — no extra dependencies

10. **Boundary tooltip on line only** ([map.py:75-94, 183-209](streamlit_app/components/map.py#L75-L94))
   - ✅ Previously, hovering anywhere inside the park boundary polygon showed a persistent `"{park_name} boundary"` tooltip, which obscured trail tooltips
   - ✅ Boundary now renders as two layers: a filled polygon (transparent stroke, no tooltip) + a separate LineString/MultiLineString of the exterior ring(s) with the tooltip
   - ✅ New `_extract_boundary_line()` helper extracts exterior rings from Polygon/MultiPolygon GeoJSON — no database changes, no extra API calls, just restructuring coordinates already in memory at render time

**Still TODO:**
- 🔲 Shareable URLs with encoded filters (deferred — low priority per user)
- 🔲 Mobile-responsive layout
- 🔲 Multi-park comparison side-by-side view

**Design decisions:**
- CartoDB Positron tiles chosen for minimal visual noise — trail lines and park boundaries are much more prominent
- Pending-flag pattern for map clicks mirrors the NLQ pending pattern — both need to mutate widget state before widget instantiation
- Hover→tooltip, click→select chosen over popup-based UX because Folium popups are static HTML (can't trigger Streamlit state changes). Tooltip gives quick park context; sidebar summary gives full details after selection
- Lat/lng matching decouples visual tooltip content from click detection logic — more robust than tooltip text matching
- Trail centroid uses mean of all coordinates (not bounding-box center) for better centering on curved trails
- Zoom level 14 for highlighted trail gives enough context to see the trail plus surrounding terrain
- Boundary split into fill + line layers so tooltip only triggers on the border stroke, not the entire polygon interior — no DB changes, just client-side GeoJSON restructuring

**Verified:**
- ✅ All 444 unit tests pass
- ✅ `ruff check` and `ruff format` clean
- ✅ Browser-tested: tooltip wrapping, park click selection, sidebar summary with description, home button
- 🔲 Needs browser testing: boundary tooltip only on border line (not inside polygon)

**Success criteria:** User hovers park pin → sees name + visit info; clicks pin → park selected + trails load; sidebar expander shows full NPS description; home button resets map to US overview; user clicks trail row → map pans to trail, trail highlighted in gold. Hovering inside park boundary shows no tooltip; hovering on the blue boundary line shows "{park_name} boundary".

---

## Troubleshooting & Lessons Learned

### Issues Encountered During Phase 1 Implementation

#### 1. ModuleNotFoundError: No module named 'streamlit_app'
**Problem:** When running `streamlit run streamlit_app/app.py`, Python couldn't find the `streamlit_app` module.

**Solution:** Added `sys.path.insert(0, str(Path(__file__).parent.parent))` to `app.py` to add the parent directory to the Python path.

**Location:** [app.py:27](streamlit_app/app.py#L27)

---

#### 2. StreamlitDuplicateElementId: Multiple elements with same ID
**Problem:** Rendering sidebar twice (once for initial filters, once with park summaries) caused duplicate widget IDs.

**Solution:**
- Added unique `key` parameter to ALL sidebar widgets (e.g., `key="filter_state_select"`)
- Fetch park summaries BEFORE rendering sidebar (not after)
- Render sidebar only once per cycle

**Pattern:** `{widget_type}_{purpose}` for key naming

**Files Changed:** [sidebar.py](streamlit_app/components/sidebar.py), [app.py](streamlit_app/app.py)

---

#### 3. State Filter Not Working with Multi-State Parks
**Problem:** Parks with `states="CA,NV"` weren't showing up when filtering by "CA".

**Solution:**
- Parse state strings: split by comma, strip whitespace, add to set
- Filter logic checks if selected state is IN the park's state list (not exact match)

**Code:**
```python
all_states_raw = [park.get("states", "") for park in all_parks if park.get("states")]
all_states = set()
for states_str in all_states_raw:
    states = [s.strip() for s in states_str.split(",")]
    all_states.update(states)

# Later, when filtering:
if filter_state in [s.strip() for s in p.get("states", "").split(",")]
```

**Location:** [sidebar.py:38-44, 75-77](streamlit_app/components/sidebar.py)

---

#### 4. Trails Table Empty / Not Displaying
**Problem:** Data table wasn't showing trails even after selecting parks.

**Root Causes:**
- LinkColumn for 3D viz links was using wrong format (HTML instead of URLs)
- Filter parameters not being applied correctly

**Solution:**
- Changed 3D viz column to use `viz_url` (string URL) instead of HTML
- Used `st.column_config.LinkColumn` with `display_text="View"`
- Fixed filter min/max logic to only pass values when different from defaults

**Location:** [data_table.py:47-59, 67-83](streamlit_app/components/data_table.py)

---

#### 5. Trail Type Filter Not Interesting
**Problem:** User feedback indicated trail type filter (path, footway, track, cycleway) wasn't useful.

**Solution:** Removed trail type filter entirely from sidebar and API client.

**Files Changed:** [sidebar.py](streamlit_app/components/sidebar.py), [api/client.py](streamlit_app/api/client.py), [app.py](streamlit_app/app.py)

---

#### 6. "Clear All" Button — StreamlitAPIException on Widget State Modification
**Problem:** Initial fix attempted to set `st.session_state["park_multiselect"] = []` after detecting the button click in the main script flow. This raised:
```
StreamlitAPIException: `st.session_state.park_multiselect` cannot be modified
after the widget with key `park_multiselect` is instantiated.
```

**Root Cause:** Streamlit doesn't allow modifying a widget's session state value once the widget has been instantiated within the same script run. By the time `render_sidebar()` returned, the multiselect was already created.

**Solution:** Use the button's `on_click` callback. Callbacks fire BEFORE the next script run, so they can safely modify widget state before widgets are instantiated.

**Pattern (use this for all "clear/reset" buttons):**
```python
def _clear_park_selection() -> None:
    if "park_multiselect" in st.session_state:
        st.session_state["park_multiselect"] = []
    st.session_state["selected_parks"] = []

clear_selection = col1.button(
    "Clear All",
    key="clear_parks_btn",
    on_click=_clear_park_selection,
)
```

**Files Changed:** [sidebar.py:15-23](streamlit_app/components/sidebar.py#L15-L23), [app.py:124-129](streamlit_app/app.py#L124-L129)

**Note:** This same pattern will be needed for the upcoming "Reset Filters" button in the Filter Trails section.

---

#### 7. Map Marker Click — StreamlitAPIException on Widget State Modification (Phase 4)

**Problem:** Clicking a park marker on the map triggered `st.session_state["park_multiselect"] = current_parks` in the map click handler, which runs AFTER the sidebar (and its multiselect widget) has been instantiated. This raised:
```
StreamlitAPIException: `st.session_state.park_multiselect` cannot be modified
after the widget with key `park_multiselect` is instantiated.
```

**Root Cause:** Same as Issue #6 — the map renders after the sidebar, so by the time we detect the click, the multiselect widget already exists. Unlike buttons, `st_folium` doesn't have an `on_click` callback.

**Solution:** Use a **pending-flag pattern** (same approach as the NLQ flow):
1. Map click handler stashes the park code in `st.session_state["pending_park_click"]` and calls `st.rerun()`
2. At the top of `main()`, BEFORE sidebar renders, `pending_park_click` is popped and used to mutate `park_multiselect`
3. The sidebar then instantiates with the updated selection

**Pattern (use for any post-widget state mutation):**
```python
# At top of main(), before widgets:
pending_park = st.session_state.pop("pending_park_click", None)
if pending_park:
    current_parks = list(st.session_state.get("park_multiselect", []))
    if pending_park not in current_parks:
        current_parks.append(pending_park)
        st.session_state["park_multiselect"] = current_parks

# After map renders:
if matched_park_code:
    st.session_state["pending_park_click"] = matched_park_code
    st.rerun()
```

**Files Changed:** [app.py:109-118, 272-288](streamlit_app/app.py)

---

### Best Practices Established

1. **Always add unique keys to widgets** - Use descriptive names, don't rely on auto-generated IDs
2. **Fetch all data before rendering** - Don't render components multiple times in one cycle
3. **Handle multi-value fields carefully** - Split, strip, and check membership (not equality)
4. **Use proper Streamlit column configs** - LinkColumn, NumberColumn, TextColumn with formatting
5. **Cache strategically** - Longer TTL for static data (parks), shorter for filtered data (trails)
6. **Session state for heavy data** - Cache park boundaries and hiked points in session state
7. **Error handling is critical** - Wrap all API calls in try/except, show user-friendly errors
8. **For "clear/reset" buttons, use `on_click` callbacks** - Never modify a widget's session state in the same run after it's been instantiated; use a callback that fires before the next rerun
9. **Surface errors instead of silently passing** - Bare `except: pass` blocks hide bugs; at minimum log to console
10. **For post-render widget state changes, use the pending-flag pattern** - Stash the desired change, `st.rerun()`, then apply it at the top of `main()` before widgets are instantiated. Used by both NLQ and map click flows.

---

## Open Questions / Future Enhancements

1. **State filtering on the map:** Should selecting a state filter auto-zoom the map to that state's bounds, or just dim non-matching parks? (Auto-zoom to state's bounds is probably better but doesn't need to be part of the early phase)

2. **Trail detail panel:** Click a trail → slide-in panel with full details + link to 3D viz? (Nice to have but not required for initial phases)

3. **Permalink/shareable URLs:** Encode filter state in URL query params so users can share a specific view (e.g., `?park=yose&hiked=false&min_length=10`)? (Another nice to have; not mandatory for initial phase)

4. **Export:** Button to download currently-filtered trails as CSV or GeoJSON? (Nice to have; not mandatory for initial phase)

5. **Comparison mode:** Select 2 parks, show side-by-side stats comparison? (Not required)

6. **Mobile responsiveness:** Collapsible sidebar, bottom sheet for trail details on small screens? (Not required for initial phase)

7. **Offline mode:** Cache park/trail data in browser storage for offline use? (Not required for initial phase)

---

## File Structure (Implemented)

```
streamlit_app/
├── app.py                 # ✅ Main Streamlit app entry point
├── components/
│   ├── __init__.py        # ✅ Module init
│   ├── map.py             # ✅ Folium map with multi-layer support
│   ├── sidebar.py         # ✅ Sidebar filters & controls
│   ├── data_table.py      # ✅ Trail data table component
│   └── nlq.py             # ✅ NLQ form, chips, widget translation, divergence detection (Phase 3)
├── api/
│   ├── __init__.py        # ✅ Module init
│   └── client.py          # ✅ HTTP client wrapper with caching + NLQ POST
├── utils/
│   ├── __init__.py        # ✅ Module init
│   ├── state.py           # ✅ Session state management
│   └── formatting.py      # ✅ Data formatting helpers
├── requirements.in        # ✅ High-level dependencies
├── requirements.txt       # ✅ Compiled with pinned versions (via pip-compile)
└── README.md              # ✅ Setup and usage docs
```

**Dependencies** are owned by the streamlit app itself, not the project root. Install from project root with `pip install -r streamlit_app/requirements.txt`.

---

## Success Metrics

**User can:**
1. See all 63 National Parks on a map
2. Filter to CA parks, select Yosemite, see 42 trails with boundaries
3. Filter to "unhiked trails over 5 miles"
4. Type "long hikes in Utah" and see the GUI auto-update to match
5. Toggle on Zion, see both Yosemite and Zion trails simultaneously
6. Click a trail in the table, see it highlighted on the map
7. Click a park marker, see the park description

**Technical:**
- Page load under 2 seconds (initial map render)
- Park selection under 1 second (fetch + render boundary + trails)
- No crashes when toggling 5+ parks
- NLQ response under 3 seconds (Ollama latency)

---

## Technical Implementation Notes

### Key Design Decisions

1. **Import Path Handling**: Added `sys.path.insert()` in `app.py` to allow imports when running `streamlit run streamlit_app/app.py` from project root.

2. **Widget Keys**: All Streamlit widgets have unique `key` parameters to prevent duplicate element ID errors during re-renders. Pattern: `{widget_type}_{purpose}` (e.g., `filter_state_select`, `park_multiselect`).

3. **Multi-State Parks**: State filter parses comma-separated values (e.g., "CA,NV") into individual states, and filtering logic checks if selected state is in the park's states list.

4. **Caching Strategy**:
   - Parks list: 5 min TTL (rarely changes)
   - Stats: 5 min TTL (rarely changes)
   - Trails: 1 min TTL (filters change frequently, but still cache briefly)
   - Park boundaries: Session state (persist until page refresh)
   - Hiked points: Session state

5. **Sidebar Rendering**: Fetch park summaries BEFORE rendering sidebar (not after) to avoid double-render and duplicate element IDs.

6. **Removed Features**: Trail type filter removed (not interesting per user feedback).

### Common Pitfalls

1. **Don't render sidebar twice** - This causes duplicate element ID errors. Fetch all data first, then render once.

2. **Session state updates** - After getting sidebar data, update `st.session_state.selected_parks` immediately to keep state in sync.

3. **Filter min/max values** - Only pass `min_length`/`max_length` to API if values differ from slider defaults (0.0/20.0).

4. **LinkColumn in dataframe** - Use `st.column_config.LinkColumn` with `display_text` parameter, not raw HTML.

5. **API error handling** - Always wrap API calls in try/except and show user-friendly errors, not just silent failures.

### API Endpoints Used

- `GET /parks` - All parks with optional `boundary=true`, `state`, `visited` filters
- `GET /trails` - Trails with `geojson=true`, `park_code`, `hiked`, `min_length`, `max_length`, `source`, `viz_3d` filters
- `GET /trails/hiked-points` - GMaps markers with optional `park_code` filter
- `GET /stats` - Aggregate statistics (displayed in header)
- `GET /parks/{park_code}/summary` - Park-specific stats for summary cards
- `GET /health` - API health check on app load

### Next Steps for Future Phases

**Phase 2:**
1. Add trail name search box (filter client-side after fetching)
2. Export button for CSV/GeoJSON download
3. Filter presets (e.g., "Unhiked long trails", "Recent hikes")

**Phase 3:** ✅ ALL COMPLETE
1. ✅ ~~Create `components/nlq.py` with NLQ input box~~
2. ✅ ~~Add chips display component for interpreted params~~
3. ✅ ~~Wire up `POST /query` endpoint~~
4. ✅ ~~Auto-set sidebar widgets from NLQ response~~
5. ✅ ~~Handle Ollama errors gracefully (503, 422, 429, 404)~~
6. ✅ ~~Resolve Docker→Ollama networking~~ — fixed via `make dev` (local API + Docker DB)
7. ✅ ~~End-to-end browser testing with live Ollama + real LLM responses~~
8. ✅ ~~Visual polish~~ — chat input, chip staleness colors, GitHub/docs links

**Phase 4:** 🔄 MOSTLY COMPLETE
1. ✅ ~~Add trail highlighting on table row click~~ — `on_select="rerun"` + `selection_mode="single-row"` + gold highlight + map reposition
2. ✅ ~~Make park markers clickable to select parks~~ — pending-flag pattern, lat/lng coordinate matching
3. ✅ ~~Park pin UX~~ — hover→tooltip (name + visit info), click→select; popups removed
4. ✅ ~~NPS descriptions in sidebar~~ — full description in park summary expander
5. ✅ ~~Quieter map tiles~~ — CartoDB Positron
6. ✅ ~~Teardrop pin markers~~ — `folium.Marker` + `folium.Icon` replaces `CircleMarker`
7. ✅ ~~Map home button~~ — 🏠 resets to US overview
8. ✅ ~~Sidebar reorder~~ — Select Parks → Park Summary → Filter Trails
9. 🔲 Shareable URLs with encoded filters (deferred — low priority)
10. 🔲 Mobile CSS improvements
11. 🔲 Multi-park comparison side-by-side view

---

## Handoff Checklist for Next Claude Conversation

### ✅ What's Ready to Use

1. **Working Streamlit App** at `streamlit_app/`
   - Run with: `streamlit run streamlit_app/app.py`
   - Dependencies: `pip install -r streamlit_app/requirements.txt`
   - API must be running on `localhost:8001` (or set `NPS_API_URL` env var)

2. **Core Functionality Working:**
   - Interactive map with park markers, boundaries, trails, GMaps points
   - Sidebar filters (state, visit status, park selection, trail filters)
   - Data table with sortable columns and 3D viz links
   - Multi-park selection
   - Session state management
   - API caching

3. **Documentation:**
   - README at `streamlit_app/README.md`
   - This plan document (updated with implementation status)
   - Code comments and docstrings in all modules

### 🔧 Recently Completed

1. **✅ COMPLETED:**
   - ✅ (2026-04-04) Added trail name search box (client-side filtering)
   - ✅ (2026-04-04) Added export buttons for CSV/GeoJSON
   - ✅ (2026-04-06) Fixed "Clear All" button using `on_click` callback pattern (avoids `StreamlitAPIException`)

2. **✅ UX Polish Pass (from User Feedback 2026-04-06):**
   - ✅ Header trimmed to just the title; reactive Parks/States/Hiked/3D-Viz metrics moved beneath the trail table
   - ✅ Selected Parks Summary fixed (was a one-rerun-lag bug — now reads from `st.session_state.park_multiselect` directly), wrapped in `st.spinner()`, parallelized with `ThreadPoolExecutor`, errors surfaced as warnings
   - ✅ "Reset Filters" button added to Filter Trails section using `on_click` callback pattern
   - ✅ Removed `🏞️` emoji from main panel title
   - ✅ Moved requirements files into `streamlit_app/requirements.{in,txt}` (treating the streamlit app as a self-contained deployable)

3. **Phase 3 (NLQ Integration) — COMPLETE (2026-04-11):**
   - ✅ Created `components/nlq.py` (~600 lines) with chat input, chips, widget translation, divergence detection
   - ✅ Added `post_nlq_query()` to `api/client.py` with status-code-aware error handling
   - ✅ Wired NLQ chat input into sidebar (top of sidebar, above "Select Parks")
   - ✅ Wired chips + pending-flag flow into `app.py`
   - ✅ All four NLQ tools handled: `search_trails`, `search_parks`, `search_stats`, `search_park_summary`
   - ✅ 359 unit tests pass; `ruff check` and `ruff format` clean

4. **UX Polish (2026-04-11):**
   - ✅ Replaced `st.form` + "Ask" button with `st.chat_input` (compact, built-in send icon, Enter-to-submit)
   - ✅ Removed redundant sidebar title (`🏞️ NPS Hikes Explorer`)
   - ✅ Improved chip staleness: green→grey color shift + caption update when filters diverge
   - ✅ Added GitHub/docs links to the app's top-right "⋮" menu (`menu_items`)
   - ✅ Fixed `make dev` to include `POSTGRES_HOST`, `POSTGRES_PORT`, and `--port 8001`
   - ✅ Added API retry logic: `/query` endpoint retries once if LLM returns plain text instead of a tool call

5. **Phase 4 (Polish & Enhancements) — IN PROGRESS (2026-04-11 → 2026-04-12):**
   - ✅ Switched map tiles to CartoDB Positron (quieter, light gray)
   - ✅ Replaced CircleMarker with teardrop pin Marker + Icon for park markers
   - ✅ Map marker click → park selection (pending-flag pattern, lat/lng coordinate matching)
   - ✅ Trail table row click → gold highlight on map + map pans to trail
   - ✅ Added `compute_trail_center()` helper, updated `get_trail_color()` with highlight support
   - ✅ Added `description` param to `fetch_parks()`, fetching with `description=True` on load
   - ✅ (2026-04-12) Park pin UX redesigned: hover→tooltip (name + visit info), click→select; popups removed
   - ✅ (2026-04-12) NPS descriptions moved to sidebar park summary expander
   - ✅ (2026-04-12) Sidebar reordered: Select Parks → Park Summary → Filter Trails
   - ✅ (2026-04-12) Map home button (🏠) resets to US overview
   - ✅ (2026-04-12) Click detection switched from tooltip text to lat/lng coordinates
   - ✅ (2026-04-12) Tooltip CSS: `white-space: normal; min-width: 200px; max-width: 350px`
   - ✅ (2026-04-12) Boundary tooltip now only on border line — polygon split into fill (no tooltip) + line (with tooltip) layers via `_extract_boundary_line()` helper
   - ✅ 444 unit tests pass; `ruff check` and `ruff format` clean

### 📝 Code Context for Next Session

**Key Files to Know:**
- `streamlit_app/app.py` - Main entry point, data fetching logic
- `streamlit_app/components/sidebar.py` - All filters and park selection
- `streamlit_app/components/map.py` - Folium map rendering
- `streamlit_app/api/client.py` - API wrapper with caching
- `streamlit_app/utils/state.py` - Session state management

**Important Patterns:**
- All widgets need unique `key` parameters
- Fetch data before rendering (no double renders)
- Use session state for heavy data (boundaries, hiked points)
- Multi-state parks: split by comma, check membership
- Filter min/max: only pass if different from defaults

**Session State Keys:**
- `selected_parks` - List of park codes
- `park_boundaries` - Dict of park_code → GeoJSON
- `park_trails` - Dict of park_code → trails data
- `park_hiked_points` - Dict of park_code → hiked points
- `highlighted_trail` - Trail ID for gold highlight on map
- `highlighted_trail_center` - [lat, lon] center of highlighted trail (for map reposition)
- `highlighted_trail_zoom` - Zoom level for highlighted trail view (14)
- `last_processed_click` - Last park coordinates processed (prevents infinite rerun loops)
- `pending_park_click` - Park code stashed by map click handler (consumed at top of main)

### 🎯 Success Metrics

**Phase 1 is done when:**
- ✅ User can select parks and see trails on map
- ✅ Filters apply correctly
- ✅ Multi-park selection works
- ✅ Table displays trails with working 3D viz links

**Phase 2 will be done when:**
- Trail name search works
- Export to CSV/GeoJSON functional
- Filter presets can be saved/loaded

**Phase 3 is done when:** ✅ PASSED
- ✅ User can type NLQ query
- ✅ Chips show interpreted params (with green→grey staleness)
- ✅ GUI widgets auto-update from NLQ
- ✅ Graceful handling of Ollama errors

### 💡 Tips for Next Claude

1. **Run the app first** - See what's working before making changes
2. **Read the troubleshooting section** - Learn from issues already solved
3. **Check session state** - Use Streamlit's built-in session state viewer
4. **Test incrementally** - Make small changes, test immediately
5. **Keep widgets keyed** - Don't break the unique key pattern
6. **Preserve caching** - Don't remove `@st.cache_data` decorators

### 🚀 Ready to Continue!

Phases 1–3 are complete. Phase 4 core features are implemented and browser-tested. Remaining Phase 4 items (shareable URLs, mobile, comparison) are lower priority.

**Development workflow:**
```bash
docker compose up db -d    # Start DB
make dev                   # API on :8001 (local, can reach Ollama)
make streamlit             # Streamlit on :8501
```

**Phase 4 browser testing checklist:**
- [x] Map loads with CartoDB Positron (light gray) tiles
- [x] Park markers are teardrop pins (green=visited, gray=unvisited, dark green=selected)
- [x] Hover park pin → tooltip shows park name + visit info (e.g., "CA (June 2023)")
- [x] Tooltip wraps properly for long names (e.g., "New River Gorge National Park & Preserve")
- [x] Click park pin → park added to sidebar multiselect, trails + boundary load
- [x] Selected Parks Summary section appears between Select Parks and Filter Trails
- [x] Park summary expander shows NPS Description
- [x] 🏠 home button on map resets to US overview
- [x] Select a park → trails appear in table below map
- [x] Click trail row in table → map pans/zooms to show that trail, trail highlighted in gold
- [x] Click a different trail row → map moves to new trail
- [x] Deselect trail row → highlight clears, map zooms back to park bounds
- [x] Change park selection → trail highlight clears
- [ ] Hover inside park boundary → no tooltip appears
- [ ] Hover on the blue boundary line → tooltip shows "{park_name} boundary"
- [ ] Park boundary still shows light blue fill

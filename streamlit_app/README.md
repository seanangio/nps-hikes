# NPS Hikes Streamlit Web Application

An interactive web application for exploring National Park hiking trails with a map-based interface. Built with Streamlit and Folium, this app provides dual-mode interaction: traditional GUI filters and natural language queries.

## Features

- **Interactive Map**: Folium-based map with multiple layers
  - Park center markers (color-coded: green=visited, gray=unvisited, dark green=selected)
  - Park boundary polygons with tooltip on the boundary line
  - Trail LineStrings (solid green=hiked, dashed gray=not hiked)
  - Trail highlighting in gold when selected from the data table
  - Hiking location markers from Google My Maps
  - Home button to reset to US overview
- **Sidebar Controls**:
  - Natural language query input (requires Ollama)
  - State filter and park multi-select with "Clear All" button
  - Visit status filter (visited/not visited)
  - Park summary cards with NPS descriptions
  - Trail filters: name search, hiked status, length range, data source, 3D viz availability
  - "Reset Filters" button
- **Natural Language Queries**: Type questions like "long trails I haven't hiked in Utah" to auto-set filters
  - Interpreted parameter chips with staleness detection
  - Stats card rendering for aggregate queries
- **Data Table**: Sortable trail table with row-click highlighting, 3D viz links, and CSV/GeoJSON export
- **Map Interactions**: Click a park marker to select it; click a trail row to highlight it on the map

## Architecture

This is a **pure frontend application** that consumes the NPS Hikes FastAPI backend via HTTP. It does not access the database directly.

```
streamlit_app/
├── app.py                 # Main Streamlit app entry point
├── api/
│   └── client.py          # HTTP client wrapper with caching + NLQ POST
├── components/
│   ├── map.py             # Folium map rendering (multi-layer)
│   ├── sidebar.py         # Sidebar filters & controls
│   ├── data_table.py      # Trail data table with selection
│   └── nlq.py             # NLQ form, chips, widget translation
├── utils/
│   ├── state.py           # Session state management
│   └── formatting.py      # Data formatting helpers
├── requirements.in        # High-level dependencies
├── requirements.txt       # Compiled with pinned versions
└── README.md              # This file
```

## Prerequisites

1. **NPS Hikes API running**: The Streamlit app requires the FastAPI backend.
2. **Python 3.12+** with the project's virtualenv activated.
3. **Ollama** (optional): Required for natural language queries. The API must be able to reach the Ollama server.

## Setup

### 1. Activate the virtualenv

```bash
source ~/.virtualenvs/nps-hikes/bin/activate
```

### 2. Install Streamlit dependencies

Run from the project root:

```bash
pip install -r streamlit_app/requirements.txt
```

Or if you want to recompile the pinned versions from the `.in` file:

```bash
pip-compile streamlit_app/requirements.in
pip install -r streamlit_app/requirements.txt
```

### 3. Start the database and API

```bash
# Start the database container
docker compose up db -d

# Start the API locally (connects to Docker DB, serves on :8001)
make dev
```

Running the API locally (not in Docker) allows it to reach Ollama on the host machine for NLQ queries.

### 4. Run the Streamlit app

In a separate terminal:

```bash
make streamlit
```

The app will open in your browser at `http://localhost:8501`.

## Configuration

### API Connection

The app connects to the API via the `NPS_API_URL` environment variable.

**Default**: `http://localhost:8001`

To override:

```bash
NPS_API_URL=http://localhost:8000 make streamlit
```

## Usage

### Basic Workflow

1. **Select Parks**: Use the sidebar to filter by state and visit status, then select one or more parks from the dropdown — or click a park marker on the map.
2. **Apply Trail Filters**: Filter trails by name, hiking status, length, data source, or 3D viz availability.
3. **Explore the Map**: Pan, zoom, and hover over park boundaries and trails for details.
4. **Browse Trails**: Scroll through the data table below the map. Click a row to highlight that trail on the map.
5. **Natural Language Search**: Type a question in the sidebar input (e.g., "long trails I haven't hiked in Utah") to auto-set filters.
6. **Export Data**: Use the CSV/GeoJSON download buttons above the data table.

## Performance Notes

### Caching

The app uses Streamlit's `@st.cache_data` decorator to cache API responses:

- **Parks list**: Cached for 5 minutes
- **Park boundaries**: Cached in session state (persists until page refresh)
- **Trails**: Fetched fresh on every filter change
- **Hiked points**: Cached in session state
- **Park summaries**: Fetched in parallel via `ThreadPoolExecutor`

### Data Size

- **Park boundary**: ~9 KB per park (simplified GeoJSON)
- **Trails with geometry**: ~400 KB per park (40-50 trails)
- **Hiked points**: ~5 KB per park

For 3 parks simultaneously: ~1.2 MB total.

## Troubleshooting

### "Cannot connect to the NPS Hikes API"

1. Check if the API is running: `curl http://localhost:8001/health`
2. If using Docker: `docker compose ps` to verify containers are up
3. Check the `NPS_API_URL` environment variable matches your setup

### "Natural language search is unavailable"

1. Check if Ollama is running: `curl http://localhost:11434/api/tags`
2. Ensure the API is running locally (not in Docker) so it can reach Ollama on the host

### Map not rendering or blank

1. Refresh the page
2. Check browser console for JavaScript errors
3. Ensure `streamlit-folium` is installed: `pip list | grep streamlit-folium`

## Development

### Adding New Features

Follow the component-based architecture:

1. **New API calls**: Add to `api/client.py`
2. **New UI components**: Add to `components/`
3. **New utilities**: Add to `utils/`
4. **Session state**: Manage via `utils/state.py`

### Code Style

- Follow PEP 8 conventions
- Use type hints for all function signatures
- Add docstrings to all public functions
- Lint with `ruff check` and format with `ruff format`

## License

This project is licensed under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).

# NPS Hikes Streamlit Web Application

An interactive web application for exploring National Park hiking trails with a map-based interface. Built with Streamlit and Folium, this app provides dual-mode interaction: traditional GUI filters and natural language queries.

## Features

### Phase 1 (Current - MVP)

- **Interactive Map**: Folium-based map with multiple layers
  - Park center markers (color-coded by visit status)
  - Park boundary polygons (when parks are selected)
  - Trail LineStrings (green for hiked, gray for not hiked)
  - Hiking location markers from Google My Maps
- **Sidebar Filters**:
  - State filter and park multi-select
  - Visit status filter (visited/not visited)
  - Trail filters: hiked status, length range, data source, trail type, 3D viz availability
- **Data Table**: Sortable table of trails with links to 3D visualizations
- **Park Summaries**: Expandable park cards showing trail statistics

### Upcoming Phases

- **Phase 2**: Enhanced trail filters and search
- **Phase 3**: Natural language query integration with visual "chips" showing interpreted parameters
- **Phase 4**: GMaps marker integration, trail highlighting, and UI polish

## Architecture

This is a **pure frontend application** that consumes the NPS Hikes FastAPI backend via HTTP. It does not access the database directly.

```
streamlit_app/
├── app.py                 # Main Streamlit app entry point
├── api/
│   └── client.py          # HTTP client wrapper for API calls
├── components/
│   ├── map.py             # Folium map rendering
│   ├── sidebar.py         # Sidebar filters & controls
│   └── data_table.py      # Trail data table
├── utils/
│   ├── state.py           # Session state management
│   └── formatting.py      # Data formatting helpers
└── README.md              # This file
```

## Prerequisites

1. **NPS Hikes API running**: The Streamlit app requires the FastAPI backend to be running.
   - Via Docker: `docker compose up -d` (exposes API on port 8001)
   - Via uvicorn: `uvicorn api.main:app --reload --port 8001`

2. **Python 3.12+** with the project's virtualenv activated

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

### 3. Start the API (if not already running)

**Option A: Using Docker (recommended)**

```bash
docker compose up -d
```

The API will be available at `http://localhost:8001`.

**Option B: Using uvicorn directly**

```bash
uvicorn api.main:app --reload --port 8001
```

### 4. Run the Streamlit app

```bash
streamlit run streamlit_app/app.py
```

The app will open in your browser at `http://localhost:8501`.

## Configuration

### API Connection

The app connects to the API via the `NPS_API_URL` environment variable.

**Default**: `http://localhost:8001` (Docker port)

To override (e.g., for local uvicorn on port 8000):

```bash
NPS_API_URL=http://localhost:8000 streamlit run streamlit_app/app.py
```

### Streamlit Configuration

You can customize Streamlit's behavior via `.streamlit/config.toml` (create if needed):

```toml
[server]
port = 8501
headless = false

[theme]
primaryColor = "#1f77b4"
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f0f2f6"
textColor = "#262730"
font = "sans serif"
```

## Usage

### Basic Workflow

1. **Select Parks**: Use the sidebar to filter by state and visit status, then select one or more parks
2. **Apply Trail Filters**: Filter trails by hiking status, length, data source, type, or 3D viz availability
3. **Explore the Map**: Pan, zoom, and click on park markers, trails, and hiking location points
4. **Browse Trails**: Scroll through the data table below the map, sorted by any column
5. **View 3D Visualizations**: Click "View 3D" links in the table to open trail elevation profiles

### Example Queries

- "Show me all trails in Yosemite" → Select Yosemite from park dropdown
- "Find long hikes I haven't done" → Set hiked status to "Not Yet Hiked", adjust length slider to 10+ miles
- "Which California parks have I visited?" → Filter by state CA, visit status "Visited Only"

## Performance Notes

### Caching

The app uses Streamlit's `@st.cache_data` decorator to cache API responses:

- **Parks list**: Cached for 5 minutes
- **Park boundaries**: Cached in session state (persists until page refresh)
- **Trails**: Fetched fresh on every filter change (not cached, since filters change frequently)
- **Hiked points**: Cached for 5 minutes

### Data Size

- **Park boundary**: ~9 KB per park (simplified GeoJSON)
- **Trails with geometry**: ~400 KB per park (40-50 trails)
- **Hiked points**: ~5 KB per park

For 3 parks simultaneously: ~1.2 MB total. Acceptable for modern browsers.

### Optimization Tips

1. **Select fewer parks** if the map feels sluggish
2. **Use filters** to reduce the number of trails rendered
3. **Refresh the page** if cached data becomes stale

## Troubleshooting

### "Cannot connect to the NPS Hikes API"

**Problem**: The app can't reach the API server.

**Solutions**:
1. Check if the API is running: `curl http://localhost:8001/health`
2. If using Docker: `docker compose ps` to verify containers are up
3. If using uvicorn: Ensure it's running on the expected port
4. Check the `NPS_API_URL` environment variable matches your setup

### "No parks match the current filters"

**Problem**: Your state/visit filters are too restrictive.

**Solutions**:
1. Reset filters to "All States" and "All Parks"
2. Check if you have any visited parks in the selected state

### Map not rendering or blank

**Problem**: Streamlit-folium component not loading.

**Solutions**:
1. Refresh the page
2. Check browser console for JavaScript errors
3. Ensure `streamlit-folium` is installed: `pip list | grep streamlit-folium`

### 3D visualization links not working

**Problem**: Clicking "View 3D" opens a 404 page.

**Solutions**:
1. Ensure the trail has elevation data collected
2. Check if the API endpoint returns the file: `curl http://localhost:8001/parks/yose/trails/TRAIL_SLUG/viz/3d`
3. Verify the `viz_3d_available` field is `true` for that trail

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
- Keep components modular and reusable

### Testing

Currently, the app relies on the API's test suite. Future work:
- Add Streamlit component tests
- Add integration tests with mocked API responses

## Roadmap

See the main [plan document](../scratch/streamlit-webapp-plan.md) for the complete roadmap.

### Phase 2: Enhanced Trail Filters (Planned)

- Advanced search (regex, full-text)
- Save filter presets
- Export trails to CSV/GeoJSON

### Phase 3: Natural Language Queries (Planned)

- NLQ input box in sidebar
- Interpreted parameter chips (e.g., `[State: CA] [Hiked: No]`)
- Auto-set GUI widgets from NLQ results
- Error handling for ambiguous queries

### Phase 4: Polish & GMaps Integration (Planned)

- Trail highlighting on table row click
- Multi-park comparison view
- Permalink/shareable URLs with encoded filters
- Mobile-responsive layout

## License

This project is licensed under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).

## Contributing

This is a personal project, but contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests if applicable
4. Submit a pull request

## Support

For issues or questions:
- **Project issues**: [GitHub Issues](https://github.com/seanangio/nps-hikes/issues)
- **API documentation**: See the [project docs](https://seanangio.github.io/nps-hikes/)

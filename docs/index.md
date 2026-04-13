# NPS Hikes

A Python project for collecting, validating, and analyzing hiking trail data from US National Parks. The project combines data from the National Park Service API, OpenStreetMap, and the USGS to build a PostGIS database of park boundaries and hiking trails, queryable through a REST API and an interactive Streamlit web app with natural language search.

## Live demos

- **[Web app](https://seanangio-nps-hikes.streamlit.app)** --- Interactive map-based explorer with park selection, trail filters, data table, and CSV/GeoJSON export. Built with Streamlit and Folium.
- **[API Swagger UI](https://seanangio-nps-hikes.onrender.com/docs)** --- Browse the API docs and query park and trail data directly.

> **Note:** Both demos run on free tiers and may take 30-60 seconds to respond on the first request while the servers wake up. Visualization endpoints (maps, elevation charts, 3D trails) and the natural language query endpoint (`/query`) are only available with a [local deployment](getting-started.md).

## Project overview

- Collect park metadata and boundaries from the NPS API.
- Extract hiking trails from OpenStreetMap and The National Map (USGS).
- Match personal hiking locations stored in Google My Maps to trail geometries.
- Explore parks and trails through a FastAPI REST API.
- Browse an interactive map, filter trails, and export data via a Streamlit web app.
- Query the API in natural language via a local LLM.

## Project structure

```
nps-hikes/
├── api/                       # FastAPI REST API
│   ├── main.py                        # API endpoints and application
│   ├── models.py                      # Pydantic response models
│   ├── queries.py                     # Database query functions
│   ├── database.py                    # Database connection management
│   └── nlq/                           # Natural language query module (Ollama LLM)
├── scripts/                   # Data collection and processing scripts
│   ├── collectors/            # Data collection from external sources
│   ├── processors/            # Data processing and analysis
│   ├── database/              # Database management utilities
│   └── orchestrator.py        # Complete pipeline orchestration
├── streamlit_app/             # Interactive Streamlit web app (API client)
├── config/                    # Configuration and settings
├── profiling/                 # Data quality analysis modules
├── tests/                     # Test suite
├── docs/                      # Documentation (this site)
└── utils/                     # Logging and utility functions
```

## Data collection pipeline

The pipeline runs six steps in the following order:

| Step | What it does | Data source |
|------|-------------|-------------|
| 1. NPS data collection | Park metadata, coordinates, and boundary polygons | [NPS API](https://www.nps.gov/subjects/developer/) |
| 2. OSM trails collection | Hiking trails within park boundaries | [OpenStreetMap](https://www.openstreetmap.org/) |
| 3. TNM trails collection | Official trail data within park boundaries | [The National Map(USGS)](https://www.usgs.gov/programs/national-geospatial-program/national-map) |
| 4. GMaps import | Hiking locations from Google My Maps KML files | KML files in `raw_data/gmaps/` |
| 5. Trail matching | Matches GMaps locations to TNM or OSM trail geometries | Internal |
| 6. Elevation collection | Elevation profiles for matched trails | [USGS Elevation Point Query Service (EPQS)](https://apps.nationalmap.gov/epqs/) |

The pipeline is resumable: each collector skips parks or trails that already have data in the database. If something interrupts a run, re-running picks up where it left off.

# NPS Hikes

A Python project for collecting, validating, and analyzing hiking trail data from U.S. National Parks. The project combines data from the National Park Service API, OpenStreetMap, and the USGS to build a PostGIS database of park boundaries and hiking trails, queryable through a REST API.

## Project overview

- Collect park metadata and boundaries from the NPS API.
- Extract hiking trails from OpenStreetMap and The National Map.
- Match personal hiking locations to trail geometries.
- Explore parks and trails through a FastAPI REST API.

## Project structure

```
nps-hikes/
├── api/                       # FastAPI REST API
│   ├── main.py                        # API endpoints and application
│   ├── models.py                      # Pydantic response models
│   ├── queries.py                     # Database query functions
│   └── database.py                    # Database connection management
├── scripts/                   # Data collection and processing scripts
│   ├── collectors/            # Data collection from external sources
│   ├── processors/            # Data processing and analysis
│   ├── database/              # Database management utilities
│   └── orchestrator.py        # Complete pipeline orchestration
├── config/                    # Configuration and settings
├── profiling/                 # Data quality analysis modules
├── tests/                     # Test suite
├── docs/                      # Documentation (this site)
└── utils/                     # Logging and utility functions
```

## Data collection pipeline

The pipeline runs six steps in order:

| Step | What it does | Data source |
|------|-------------|-------------|
| 1. NPS Data Collection | Park metadata, coordinates, and boundary polygons | [NPS API](https://www.nps.gov/subjects/developer/) |
| 2. OSM Trails Collection | Hiking trails within park boundaries | [OpenStreetMap](https://www.openstreetmap.org/) |
| 3. TNM Trails Collection | Official trail data within park boundaries | [The National Map](https://www.usgs.gov/programs/national-geospatial-program/national-map) |
| 4. GMaps Import | Hiking locations from Google My Maps KML files | KML files in `raw_data/gmaps/` |
| 5. Trail Matching | Matches GMaps locations to TNM or OSM trail geometries | Internal |
| 6. Elevation Collection | Elevation profiles for matched trails | [USGS EPQS](https://apps.nationalmap.gov/epqs/) |

The pipeline is resumable: each collector skips parks or trails that already have data in the database. If a run is interrupted, re-running picks up where it left off.

# NPS Hikes

A Python project for collecting, validating, and analyzing hiking trail data from U.S. National Parks. The project combines official National Park Service (NPS) data with OpenStreetMap (OSM) and National Map trail information to create a rich dataset of park boundaries and hiking trails, queryable through a REST API.

## What it does

- **Collect** park metadata and boundary data from the National Park Service API
- **Extract** hiking trail data from OpenStreetMap and The National Map within park boundaries
- **Match** your personal hiking locations to trail geometries
- **Store** data in a PostGIS database with spatial indexing
- **Explore** trails and parks through a FastAPI REST API with interactive documentation

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

## Database schema

### Core tables

- **parks**: Park metadata (codes, names, coordinates, descriptions, visit dates)
- **park_boundaries**: Spatial boundaries as MultiPolygon geometries in WGS84
- **osm_hikes**: Aggregated trail geometries from OpenStreetMap (segments with same name combined into MultiLineString)
- **tnm_hikes**: Trail data from The National Map with detailed trail characteristics
- **gmaps_hiking_locations**: Google Maps hiking location points with coordinates
- **gmaps_hiking_locations_matched**: Matched locations with trail correlation results
- **usgs_trail_elevations**: Elevation profile data for matched trails

### Key features

- Spatial indexing with PostGIS GIST indexes for performance
- Foreign key relationships for data integrity across tables
- Composite primary keys for trail uniqueness (park_code + osm_id)
- Coordinate validation with proper range constraints

## Data sources

- Park boundaries and metadata: [National Park Service API](https://www.nps.gov/subjects/developer/)
- Trail data: [OpenStreetMap](https://www.openstreetmap.org/) via Overpass API
- Trail data: [The National Map](https://www.usgs.gov/programs/national-geospatial-program/national-map) via USGS
- Elevation data: [USGS Elevation Point Query Service](https://apps.nationalmap.gov/epqs/)
- Coordinate systems: EPSG:4326 (WGS84) for geographic data

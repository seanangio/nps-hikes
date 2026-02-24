# Data Sources and Schema

## External sources

The project collects data from the following APIs.

### National Park Service

The [NPS API](https://www.nps.gov/subjects/developer/) requires a free API key, and provides park metadata and boundary geometries.

- The collector queries the `/parks` endpoint for park names, codes, designations, coordinates, descriptions, and contact information, filtering for National Park designations.
- A second pass fetches GeoJSON boundary polygons from the `/mapdata/parkboundaries/{park_code}` endpoint. The collector standardizes boundaries to MultiPolygon format with bounding boxes calculated for downstream spatial queries.

### OpenStreetMap

The pipeline collects trail geometries from [OpenStreetMap](https://www.openstreetmap.org/) via the Overpass API using the `osmnx` library. Note that the collector:

- Queries for paths and footways (`highway=path|footway`) within each park's boundary polygon.
- Retains named trails only.
- Aggregates segments sharing the same name into single MultiLineString records.
- Calculates trail lengths in miles using a projected coordinate system `EPSG:5070`.
- Clips trails to the park boundary before storage.

### The National Map

[The National Map](https://www.usgs.gov/programs/national-geospatial-program/national-map) provides official USGS trail data through an ArcGIS REST endpoint. The collector queries using each park's bounding box and returns trail geometries along with detailed attributes: trail type, trail number, length, and use flags (hiker, bicycle, pack/saddle, cross-country ski, etc.). Like OSM trails, the collector aggregates segments by name, clips to the park boundary, and recalculates lengths in the projected CRS.

### USGS Elevation Point Query Service

The [USGS EPQS](https://apps.nationalmap.gov/epqs/) returns elevation in meters for individual latitude/longitude coordinates. The collector samples points along matched trail geometries at regular intervals (default 50 meters) and queries the service for each point. The collector caches results locally to avoid redundant API calls. A three-stage validation pipeline checks API responses, individual point values, and the complete elevation profile. It treates the USGS sentinel value of `-1,000,000` as missing data.

### Coordinate systems

All geographic data uses `EPSG:4326 (WGS84)`. Length calculations use `EPSG:5070 (NAD83/Conus Albers)` for accurate distance measurements in meters.

## Internal sources

For the following two sources, you can replace the author's files with your own.

### Park visit log

A CSV file (`raw_data/park_visit_log.csv`) recording which national parks you've visited, with park name, month, and year. The NPS collector uses this to tag parks as visited or unvisited, enabling filtered queries through the API. See [Park visit log](getting-started.md#park-visit-log) for formatting details.

### Google My Maps KML files

KML files exported from [Google My Maps](https://www.google.com/maps/d/) containing named hiking location points, organized into layers by 4-letter park code. The pipeline imports these points, matches them to the nearest trail geometries from TNM or OSM, and then collects elevation profiles for the matched trails. See [Google My Maps hiking data](getting-started.md#google-my-maps-hiking-data) for export instructions.

## Database schema

### Core tables

The pipeline orchestrator creates the following tables:

| Table | Description |
|---|---|
| **parks** | Park metadata (codes, names, coordinates, descriptions, visit dates) |
| **park_boundaries** | Spatial boundaries as MultiPolygon geometries in WGS84 |
| **osm_hikes** | Aggregated trail geometries from OpenStreetMap (segments with same name combined into MultiLineString) |
| **tnm_hikes** | Trail data from The National Map with detailed trail characteristics |
| **gmaps_hiking_locations** | Google Maps hiking location points with coordinates |
| **gmaps_hiking_locations_matched** | Matched locations with trail correlation results |
| **usgs_trail_elevations** | Elevation profile data for matched trails |

### Key features

- Spatial indexing with PostGIS GIST indexes for performance
- Foreign key relationships for data integrity across tables
- Composite primary keys for trail uniqueness (`park_code` + `osm_id`)
- Coordinate validation with proper range constraints

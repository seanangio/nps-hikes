# Data sources and schema

## External sources

### National Park Service API

The [NPS API](https://www.nps.gov/subjects/developer/) provides park metadata and boundary geometries. The collector queries the `/parks` endpoint for park names, codes, designations, coordinates, descriptions, and contact information, filtering for National Park designations. A second pass fetches GeoJSON boundary polygons from the `/mapdata/parkboundaries/{park_code}` endpoint. Boundaries are standardized to MultiPolygon format with bounding boxes calculated for downstream spatial queries. Requires a free API key.

### OpenStreetMap

Trail geometries are collected from [OpenStreetMap](https://www.openstreetmap.org/) via the Overpass API using the `osmnx` library. The collector queries for paths and footways (`highway=path|footway`) within each park's boundary polygon. Only named trails are kept. Segments sharing the same name are aggregated into single MultiLineString records, and trail lengths are calculated in miles using a projected coordinate system (EPSG:5070). Trails are clipped to the park boundary before storage.

### The National Map

[The National Map](https://www.usgs.gov/programs/national-geospatial-program/national-map) provides official USGS trail data through an ArcGIS REST endpoint. The collector queries using each park's bounding box and returns trail geometries along with detailed attributes: trail type, trail number, length, and use flags (hiker, bicycle, pack/saddle, cross-country ski, etc.). Like OSM trails, segments are aggregated by name, clipped to the park boundary, and lengths are recalculated in the projected CRS.

### USGS Elevation Point Query Service

The [USGS EPQS](https://apps.nationalmap.gov/epqs/) returns elevation in meters for individual latitude/longitude coordinates. The collector samples points along matched trail geometries at regular intervals (default 50 meters) and queries the service for each point. Results are cached locally to avoid redundant API calls. A three-stage validation pipeline checks API responses, individual point values, and the complete elevation profile. The USGS sentinel value of -1,000,000 is treated as missing data.

### Coordinate systems

All geographic data uses EPSG:4326 (WGS84). Length calculations use EPSG:5070 (NAD83/Conus Albers) for accurate distance measurements in meters.

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

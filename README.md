# NPS Hikes - National Park Hiking Trail Data Collection & Analysis

[![Tests](https://img.shields.io/badge/tests-passing-brightgreen)]() [![Python](https://img.shields.io/badge/python-3.12-blue)]()

A comprehensive Python project for collecting, validating, and analyzing hiking trail data from U.S. National Parks. The project combines official National Park Service (NPS) data with OpenStreetMap (OSM) trail information to create a rich dataset of park boundaries and hiking trails.

> **Note**: This README was generated with assistance from Claude AI to provide comprehensive project documentation.

## 🏔️ Overview

This project enables researchers, park enthusiasts, and data analysts to:

- **Collect** park metadata and boundary data from the National Park Service API
- **Extract** hiking trail data from OpenStreetMap within park boundaries  
- **Validate** and clean spatial data with comprehensive quality checks
- **Store** data in both PostgreSQL/PostGIS databases and portable file formats
- **Analyze** trail patterns, data quality, and park coverage statistics
- **Profile** data quality across multiple dimensions

## 🚀 Key Features

### Data Collection Pipeline
- **NPS API Integration**: Automated collection of park metadata, coordinates, and boundary polygons
- **OSM Trail Mining**: Intelligent extraction of hiking trails from OpenStreetMap's rich dataset
- **Spatial Processing**: Precise boundary filtering and trail intersection analysis
- **Rate Limiting**: Respectful API usage with configurable delays
- **Resumable Operations**: Interrupt and resume large collection jobs without data loss

### Data Quality & Validation
- **Geometry Validation**: Ensures valid spatial data and removes malformed geometries
- **Length Filtering**: Removes unrealistically short (<0.01 mi) or long (>50 mi) trails
- **Duplicate Detection**: Identifies and removes duplicate trails and park records
- **Coordinate Validation**: Validates latitude/longitude coordinates are within valid ranges
- **Data Profiling**: Comprehensive quality metrics and statistical analysis

### Storage & Output Formats
- **PostgreSQL/PostGIS**: Production-ready spatial database with proper indexing
- **GeoPackage**: Portable spatial data format for desktop GIS applications
- **CSV/JSON**: Standard formats for data interchange and analysis
- **Interactive Maps**: HTML visualizations using Folium

## 📊 Project Structure

```
nps-hikes/
├── nps_collector.py           # NPS API data collection
├── osm_hikes_collector.py     # OpenStreetMap trail extraction
├── db_writer.py               # Unified database operations
├── config/                    # Configuration and settings
├── profiling/                 # Data quality analysis modules
│   ├── modules/               # Individual profiling modules
│   └── queries/               # SQL analysis queries
├── tests/                     # Comprehensive test suite
│   ├── unit/                  # Unit tests with mocking
│   └── integration/           # Integration tests
├── utils/                     # Logging and utility functions
```

## 🛠️ Installation

### Prerequisites
- Python 3.12+
- PostgreSQL with PostGIS extension
- NPS API key (free from [NPS API](https://www.nps.gov/subjects/developer/api-documentation.htm))

### Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd nps-hikes
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your database credentials and NPS API key
   ```

4. **Set up the database**
   ```sql
   CREATE DATABASE nps_hikes;
   CREATE EXTENSION postgis;
   ```

## 🎯 Quick Start

### 1. Collect Park Data
```bash
# Collect park metadata and boundaries
python nps_collector.py --write-db

# Test with specific parks
python nps_collector.py --parks YELL,GRCA --test-limit 2
```

### 2. Extract Hiking Trails
```bash
# Collect trails for all parks
python osm_hikes_collector.py --write-db

# Process specific parks with rate limiting
python osm_hikes_collector.py --parks YELL,ZION --rate-limit 1.0
```

### 3. Analyze Data Quality
```bash
# Run comprehensive data profiling
python -m profiling.orchestrator

# Profile specific modules
python -m profiling.orchestrator nps_parks data_quality
```

## 📋 Configuration

The project uses a centralized configuration system in `config/settings.py`:

- **Database connections**: PostgreSQL/PostGIS settings
- **API settings**: NPS API endpoints and rate limits  
- **Data validation**: Quality thresholds and filters
- **File paths**: Output directories and file formats
- **Coordinate systems**: CRS definitions for spatial operations

## 🧪 Testing

The project includes a comprehensive test suite:

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=. --cov-report=html

# Run specific test modules
pytest tests/unit/test_db_writer.py -v
```

**Test Coverage:**
- **Unit tests**: Mock external dependencies (APIs, databases)
- **Data validation**: Edge cases and error handling
- **Database operations**: Schema validation and data integrity
- **Spatial operations**: Geometry processing and validation

## 📈 Data Profiling

The profiling system provides comprehensive insights into data quality and completeness across all datasets.

### Running Profiling

```bash
# Run all enabled profiling modules
python -m profiling.orchestrator

# Run specific modules
python -m profiling.orchestrator osm_hikes tnm_hikes

# List all available modules and their status
python -m profiling.orchestrator --list-modules

# Run with verbose output
python -m profiling.orchestrator --verbose data_freshness

# Get help
python -m profiling.orchestrator --help
```

### Available Modules
- **nps_parks**: NPS park statistics and data analysis
- **nps_geography**: NPS geographic and spatial analysis  
- **data_quality**: Cross-table data quality and validation checks
- **visualization**: Data visualization and maps
- **osm_hikes**: OSM hiking trails analysis
- **tnm_hikes**: TNM hiking trails analysis
- **data_freshness**: Data freshness monitoring across all tables

### Sample Metrics
- Park collection success rates by state
- Trail length distributions and outliers
- Coordinate precision and accuracy analysis
- Missing data patterns and completeness scores
- Data freshness monitoring with staleness thresholds
- Cross-table referential integrity validation

## 🔧 Database Schema

### Core Tables
- **parks**: Park metadata (codes, names, coordinates, descriptions)
- **park_boundaries**: Spatial boundaries as MultiPolygon geometries
- **osm_hikes**: Trail geometries with attributes (name, length, type) from OpenStreetMap via OSMnx

### Key Features
- Proper spatial indexing for performance
- Foreign key relationships for data integrity
- Composite primary keys for trail uniqueness
- Support for both projected and geographic coordinate systems

## 📚 Example Usage

### Load and Analyze Data
```python
import geopandas as gpd
from db_writer import get_postgres_engine

# Load park boundaries
engine = get_postgres_engine()
parks = gpd.read_postgis("SELECT * FROM park_boundaries", engine)

# Load trails for a specific park
trails = gpd.read_postgis(
    "SELECT * FROM osm_hikes WHERE park_code = 'YELL'", 
    engine
)

# Calculate total trail miles per park
summary = trails.groupby('park_code')['length_mi'].sum()
```

### Create Interactive Maps
```python
import folium
from profiling.modules.visualization import create_park_map

# Create interactive map with park boundaries and trails
map_obj = create_park_map(parks, trails)
map_obj.save('park_trails_map.html')
```

## 🙏 Acknowledgments

- **National Park Service** for providing comprehensive park data via their API
- **OpenStreetMap community** for maintaining detailed trail information
- **Python geospatial ecosystem**: GeoPandas, Shapely, OSMnx, Folium, and PostGIS

## 📞 Support

For questions, issues, or contributions:
- Open an issue on GitHub
- Check existing documentation in the `docs/` folder
- Review the comprehensive test suite for usage examples

---

**Data Sources:**
- Park boundaries and metadata: [National Park Service API](https://www.nps.gov/subjects/developer/)  
- Trail data: [OpenStreetMap](https://www.openstreetmap.org/) via Overpass API
- Coordinate systems: EPSG:4326 (WGS84) for geographic data
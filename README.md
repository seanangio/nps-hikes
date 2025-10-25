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
- **Static Maps**: PNG visualizations for data validation

## 📊 Project Structure

```
nps-hikes/
├── scripts/                   # Data collection and processing scripts
│   ├── collectors/            # Data collection from external sources
│   │   ├── nps_collector.py           # NPS API data collection
│   │   ├── osm_hikes_collector.py     # OpenStreetMap trail extraction
│   │   ├── tnm_hikes_collector.py     # The National Map trail data
│   │   ├── usgs_elevation_collector.py # USGS elevation data
│   │   └── gmaps_hiking_importer.py   # Google Maps hiking locations
│   ├── processors/            # Data processing and analysis
│   │   └── trail_matcher.py           # Trail matching and correlation
│   ├── database/              # Database management utilities
│   │   ├── db_writer.py               # Unified database operations
│   │   └── reset_database.py          # Database reset utilities
│   └── orchestrator.py        # Complete pipeline orchestration
├── config/                    # Configuration and settings
├── profiling/                 # Data quality analysis modules
│   ├── modules/               # Individual profiling modules
│   └── queries/               # SQL analysis queries
├── tests/                     # Comprehensive test suite
│   ├── unit/                  # Unit tests with mocking
│   └── integration/           # Integration tests
├── utils/                     # Logging and utility functions
├── cursor-mcp-config.json    # MCP PostgreSQL server configuration
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

### Option 1: Complete Pipeline (Recommended)
```bash
# Run the entire data collection pipeline
python scripts/orchestrator.py --write-db

# Test with limited parks for development
python scripts/orchestrator.py --test-limit 3 --write-db

# Dry run to see execution plan
python scripts/orchestrator.py --dry-run --write-db
```

### Option 2: Individual Components
```bash
# 1. Collect park metadata and boundaries
python scripts/collectors/nps_collector.py --write-db

# 2. Extract hiking trails from OpenStreetMap
python scripts/collectors/osm_hikes_collector.py --write-db

# 3. Collect additional trails from The National Map
python scripts/collectors/tnm_hikes_collector.py --write-db

# 4. Import Google Maps hiking locations
python scripts/collectors/gmaps_hiking_importer.py --write-db

# 5. Match GMaps locations to trail linestrings
python scripts/processors/trail_matcher.py --write-db

# 6. Collect elevation data for matched trails
python scripts/collectors/usgs_elevation_collector.py --write-db
```

### 3. Analyze Data Quality
```bash
# Run comprehensive data profiling
python -m profiling.orchestrator

# Profile specific modules
python -m profiling.orchestrator nps_parks data_quality
```

## 🔄 Pipeline Orchestration

The project includes a comprehensive pipeline orchestrator (`scripts/orchestrator.py`) that executes the complete data collection workflow in the correct dependency order:

### Pipeline Steps
1. **NPS Data Collection** - Collect park metadata and boundaries (foundation)
2. **OSM Trails Collection** - Collect hiking trails from OpenStreetMap
3. **TNM Trails Collection** - Collect trails from The National Map
4. **GMaps Import** - Import Google Maps hiking locations
5. **Trail Matching** - Match GMaps locations to trail linestrings
6. **Elevation Collection** - Collect elevation data for matched trails

### Orchestrator Features
- **Sequential execution** with dependency management
- **Fail-fast error handling** with detailed logging
- **Pre-flight checks** for database connectivity and file structure
- **Dry run support** for testing execution plans
- **Timeout protection** for long-running processes
- **Progress tracking** with comprehensive logging

### Usage Examples
```bash
# Full pipeline with database writes
python scripts/orchestrator.py --write-db

# Test mode with limited parks
python scripts/orchestrator.py --test-limit 3 --write-db

# Dry run to see execution plan
python scripts/orchestrator.py --dry-run --write-db

# Get help and see all options
python scripts/orchestrator.py --help
```

## 🔧 Database Access with MCP Server

The project includes an MCP (Model Context Protocol) PostgreSQL server configuration for enhanced database access and querying capabilities.

### MCP Server Setup
The MCP server is configured in `cursor-mcp-config.json` and provides:
- **Read-only database access** with safety restrictions
- **Data masking** for sensitive information
- **Structured query capabilities** through the MCP interface
- **Connection management** with proper environment variable handling

### Configuration
The MCP server configuration is stored in `cursor-mcp-config.json` and uses environment variables for sensitive credentials:

```json
{
    "mcpServers": {
        "postgresql": {
            "command": "npx",
            "args": ["mcp-postgresql-server"],
            "env": {
                "POSTGRES_HOST": "localhost",
                "POSTGRES_PORT": "5432",
                "POSTGRES_DB": "nps_hikes_db",
                "POSTGRES_USER": "${POSTGRES_USER}",
                "POSTGRES_PASSWORD": "${POSTGRES_PASSWORD}",
                "POSTGRES_QUERY_LEVEL": "readonly",
                "POSTGRES_DATA_MASKING": "true"
            }
        }
    }
}
```

**Important**: Replace `${POSTGRES_USER}` and `${POSTGRES_PASSWORD}` with your actual database credentials or use environment variables.

### Benefits
- **Enhanced querying** through natural language interfaces
- **Data exploration** with automatic schema understanding
- **Safety features** including read-only access and data masking
- **Integration** with development tools and AI assistants

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

### Profiling Results Organization

Profiling outputs are organized in `profiling_results/` by module for easy navigation:

```
profiling_results/
├── data_freshness/           # Collection status and completeness
├── data_quality/            # Data consistency and validation checks
├── gmaps_hiking_locations/  # Google Maps analysis and coverage
├── nps_geography/           # Geographic boundary and coordinate analysis
├── nps_parks/              # NPS parks collection and state counts
├── osm_hikes/              # OpenStreetMap trail analysis
├── tnm_hikes/              # The National Map hikes analysis
├── trail_matching/         # Trail matching confidence and distance analysis
├── usgs_elevation/         # USGS elevation data analysis
│   ├── park_summaries/     # Park-specific elevation summaries
│   └── park_stats/         # Park-specific elevation statistics
└── visualizations/          # Maps and charts
    ├── elevation_changes/   # Elevation change matrices (PNG)
    └── static_maps/        # Static map visualizations (PNG)
```

**File Naming Convention:**
- General analysis files use descriptive names (e.g., `collection_status_summary.csv`)
- Park-specific files use park codes (e.g., `acad.csv` for Acadia National Park)
- Statistical files include `_stats` suffix (e.g., `acad_stats.csv`)

## 🔧 Database Schema

### Core Tables
- **parks**: Park metadata (codes, names, coordinates, descriptions, visit dates)
- **park_boundaries**: Spatial boundaries as MultiPolygon geometries in WGS84
- **osm_hikes**: Trail geometries with attributes (name, length, type) from OpenStreetMap
- **tnm_hikes**: Trail data from The National Map with detailed trail characteristics
- **gmaps_hiking_locations**: Google Maps hiking location points with coordinates
- **gmaps_hiking_locations_matched**: Matched locations with trail correlation results
- **usgs_trail_elevations**: Elevation profile data for matched trails

### Key Features
- **Spatial indexing** with PostGIS GIST indexes for performance
- **Foreign key relationships** for data integrity across tables
- **Composite primary keys** for trail uniqueness (park_code + osm_id)
- **Coordinate validation** with proper range constraints
- **Support for both projected and geographic coordinate systems**
- **Comprehensive indexing** for common query patterns

## 📚 Example Usage

### Load and Analyze Data
```python
import geopandas as gpd
from scripts.database.db_writer import get_postgres_engine

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

### Create Static Maps
```python
from profiling.modules.visualization import VisualizationProfiler

# Create static maps for all parks
profiler = VisualizationProfiler()
profiler.run_all()
```

## 🙏 Acknowledgments

- **National Park Service** for providing comprehensive park data via their API
- **OpenStreetMap community** for maintaining detailed trail information
- **Python geospatial ecosystem**: GeoPandas, Shapely, OSMnx, and PostGIS

## 📞 Support

For questions, issues, or contributions:
- Open an issue on GitHub
- Review the comprehensive test suite for usage examples
- Check the project's configuration files and examples in the codebase

---

**Data Sources:**
- Park boundaries and metadata: [National Park Service API](https://www.nps.gov/subjects/developer/)  
- Trail data: [OpenStreetMap](https://www.openstreetmap.org/) via Overpass API
- Coordinate systems: EPSG:4326 (WGS84) for geographic data
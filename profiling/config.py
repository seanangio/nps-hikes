"""
Configuration for profiling modules.

This centralizes all profiling configuration, making it easy to:
- Enable/disable modules
- Control which queries run
- Set module-specific parameters
- Manage dependencies between modules
"""

from typing import TypedDict


class ModuleConfig(TypedDict):
    enabled: bool
    description: str
    queries: list[str]
    dependencies: list[str]
    output_prefix: str


class ProfilingSettingsConfig(TypedDict):
    output_directory: str
    save_csv: bool
    print_summaries: bool
    continue_on_error: bool
    parallel_execution: bool


PROFILING_MODULES: dict[str, ModuleConfig] = {
    "nps_parks": {
        "enabled": True,
        "description": "NPS park statistics and data analysis",
        "queries": [
            "park_counts_by_state.sql",
            "collection_status_summary.sql",
            "data_completeness_summary.sql",
        ],
        "dependencies": [],
        "output_prefix": "nps_parks",
    },
    "nps_geography": {
        "enabled": True,
        "description": "NPS geographic and spatial analysis",
        "queries": [
            "regional_breakdown.sql",
            "coordinate_quality.sql",
            "boundary_coverage.sql",
        ],
        "dependencies": [],
        "output_prefix": "nps_geography",
    },
    "data_quality": {
        "enabled": True,
        "description": "Cross-table data quality and validation checks",
        "queries": [
            "referential_integrity.sql",
            "data_consistency.sql",
            "missing_data_summary.sql",
            "duplicate_detection.sql",
        ],
        "dependencies": [],
        "output_prefix": "data_quality",
    },
    "visualization": {
        "enabled": True,
        "description": "Data visualization and maps",
        "queries": [],  # visualization is done in Python
        "dependencies": [],
        "output_prefix": "visualization",
    },
    "osm_hikes": {
        "enabled": True,
        "description": "OSM hiking trails analysis",
        "queries": [
            "trails_summary_by_park.sql",
            "trail_type_analysis.sql",
            "trail_length_distribution.sql",
            "trail_data_quality.sql",
        ],
        "dependencies": [],
        "output_prefix": "osm_hikes",
    },
    "data_freshness": {
        "enabled": True,
        "description": "Data freshness monitoring across all tables",
        "queries": [
            "parks_staleness.sql",
            "boundaries_staleness.sql",
            "osm_staleness.sql",
            "tnm_staleness.sql",
        ],
        "dependencies": [],
        "output_prefix": "data_freshness",
    },
    "gmaps_hiking_locations": {
        "enabled": True,
        "description": "Google Maps hiking locations analysis",
        "queries": [
            "basic_summary.sql",
            "park_analysis.sql",
            "park_coverage.sql",
        ],
        "dependencies": [],
        "output_prefix": "gmaps",
    },
    "trail_matching": {
        "enabled": True,
        "description": "Trail matching analysis and quality metrics",
        "queries": [
            "match_summary.sql",
            "confidence_distribution.sql",
            "park_analysis.sql",
            "distance_analysis.sql",
            "unmatched_analysis.sql",
            "source_comparison.sql",
        ],
        "dependencies": ["gmaps_hiking_locations"],
        "output_prefix": "trail_matching",
    },
    "usgs_elevation_stats": {
        "enabled": True,
        "description": "USGS elevation data analysis and quality metrics",
        "queries": [
            "trail_elevation_stats.sql",
            "park_elevation_summary.sql",
            "trail_grades.sql",
            "steepest_segments.sql",
            "data_quality.sql",
            "collection_status.sql",
        ],
        "dependencies": ["trail_matching"],
        "output_prefix": "usgs_elevation",
    },
    "usgs_elevation_viz": {
        "enabled": True,
        "description": "USGS elevation visualization and matrix generation",
        "queries": [],  # visualization is done in Python
        "dependencies": ["usgs_elevation_stats"],
        "output_prefix": "usgs_elevation_viz",
    },
    "trail_3d_viz": {
        "enabled": True,
        "description": "Interactive 3D trail elevation visualizations",
        "queries": [],  # visualization is done in Python with Plotly
        "dependencies": ["usgs_elevation_stats"],
        "output_prefix": "trail_3d_viz",
    },
    "us_park_map": {
        "enabled": True,
        "description": "US overview map showing visited and unvisited national parks",
        "queries": [],  # visualization is done in Python
        "dependencies": [],
        "output_prefix": "us_park_map",
    },
}

# Global profiling settings
PROFILING_SETTINGS: ProfilingSettingsConfig = {
    "output_directory": "profiling_results",
    "save_csv": True,
    "print_summaries": False,  # Don't print data to terminal
    "continue_on_error": True,  # Continue if one module fails
    "parallel_execution": False,  # For future: run modules in parallel
}

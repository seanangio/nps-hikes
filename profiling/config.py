"""
Configuration for profiling modules.

This centralizes all profiling configuration, making it easy to:
- Enable/disable modules
- Control which queries run
- Set module-specific parameters
- Manage dependencies between modules
"""

PROFILING_MODULES = {
    "basic_stats": {
        "enabled": True,
        "description": "Basic park statistics and counts",
        "queries": [
            "park_counts_by_state.sql",
            "collection_status_summary.sql",
            "data_completeness_summary.sql",
        ],
        "dependencies": [],
        "output_prefix": "basic_stats",
    },
    "geographic_analysis": {
        "enabled": True,
        "description": "Geographic and spatial analysis",
        "queries": [
            "regional_breakdown.sql",
            "coordinate_quality.sql",
            "boundary_coverage.sql",
        ],
        "dependencies": [],
        "output_prefix": "geographic",
    },
    "data_quality": {
        "enabled": True,
        "description": "Data quality and validation checks",
        "queries": ["missing_data.sql", "validation_checks.sql"],
        "dependencies": [],
        "output_prefix": "quality",
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
}

# Global profiling settings
PROFILING_SETTINGS = {
    "output_directory": "profiling_results",
    "save_csv": True,
    "print_summaries": False,  # Don't print data to terminal
    "continue_on_error": True,  # Continue if one module fails
    "parallel_execution": False,  # For future: run modules in parallel
}

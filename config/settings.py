"""
Configuration settings for the NPS Hikes project.

This module centralizes all configuration values and provides a single source of truth for all
configurable parameters.

The configuration system uses context-aware validation to support different operational modes:
- API operations (CSV output): Requires only NPS_API_KEY
- Database operations (profiling, OSM collection): Requires only database credentials
- API + Database operations (--write-db flag): Requires both NPS_API_KEY and database credentials

This design allows components to run independently without unnecessary dependencies.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """
    Central configuration class for the NPS Hikes project.

    This class consolidates all configuration values including API settings,
    database connections, file paths, and processing parameters.
    """

    # API Configuration
    APP_NAME: str = "Python-NPS-Collector"
    APP_VERSION: str = "1.0"
    API_BASE_URL: str = "https://developer.nps.gov/api/v1"
    API_KEY: str | None = None
    USER_EMAIL: str = "unknown@example.com"

    # API Request Settings
    REQUEST_TIMEOUT: int = 30
    DEFAULT_DELAY_SECONDS: float = 1.0

    # API and request settings
    RATE_LIMIT_WARNING_THRESHOLD: int = 50
    API_RESULT_LIMIT: int = 10
    DEFAULT_CRS: str = "EPSG:4326"

    # Retry Configuration
    PARK_SEARCH_MAX_RETRIES: int = 2
    PARK_SEARCH_RETRY_DELAY: float = 3.0
    BOUNDARY_MAX_RETRIES: int = 3
    BOUNDARY_RETRY_DELAY: float = 5.0

    # NPS Bulk Fetch Settings
    NPS_BULK_FETCH_LIMIT: int = 50
    NPS_DESIGNATION_FILTERS: list = [
        "National Park",
        "National Park & Preserve",
        "National Parks",
        "National and State Parks",
    ]
    # Parks with missing/empty designation in the API that should still be included
    NPS_ADDITIONAL_PARK_CODES: list = [
        "npsa",  # National Park of American Samoa (designation is empty in NPS API)
    ]

    # Database Configuration
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "nps_hikes_db"
    DB_USER: str = "postgres"
    DB_PASSWORD: str | None = None
    DB_SSLMODE: str | None = None

    # File Paths
    DEFAULT_INPUT_CSV: str = "raw_data/park_visit_log.csv"
    DEFAULT_OUTPUT_CSV: str = "artifacts/park_data_collected.csv"
    DEFAULT_OUTPUT_GPKG: str = "artifacts/park_boundaries_collected.gpkg"
    NPS_LOG_FILE: str = "logs/nps_collector.log"

    # OSM Collection Settings
    OSM_DEFAULT_OUTPUT_GPKG: str = "artifacts/osm_hikes.gpkg"
    OSM_DEFAULT_RATE_LIMIT: float = 1.0
    OSM_LENGTH_CRS: str = "EPSG:5070"  # NAD83 / Conus Albers for length calculations
    OSM_TRAIL_TAGS: dict = {"highway": ["path", "footway"]}
    OSM_LOG_FILE: str = "logs/osm_collector.log"
    OSM_REQUIRED_COLUMNS: list = [
        "osm_id",
        "park_code",
        "highway",
        "geometry",
        "geometry_type",
        "length_miles",
    ]
    OSM_ALL_COLUMNS: list = [
        "osm_id",
        "park_code",
        "highway",
        "name",
        "source",
        "length_miles",
        "geometry_type",
        "geometry",
    ]
    # OSM Validation Settings
    OSM_MIN_TRAIL_LENGTH_MILES: float = 0.01
    OSM_MAX_TRAIL_LENGTH_MILES: float = 200.0  # Increased for aggregated trail segments

    # TNM Collection Settings
    TNM_API_BASE_URL: str = (
        "https://cartowfs.nationalmap.gov/arcgis/rest/services/transportation/MapServer/8"
    )
    TNM_DEFAULT_OUTPUT_GPKG: str = "artifacts/tnm_hikes.gpkg"
    TNM_DEFAULT_RATE_LIMIT: float = 1.0
    TNM_TRAIL_AGGREGATION_DISTANCE: float = 50.0  # meters for trail continuity
    TNM_MIN_TRAIL_LENGTH_MI: float = 0.01  # minimum length after aggregation
    TNM_LOG_FILE: str = "logs/tnm_collector.log"

    # GMaps Collection Settings
    GMAPS_INPUT_DIRECTORY: str = "raw_data/gmaps"
    GMAPS_LOG_FILE: str = "logs/gmaps_importer.log"

    # USGS Elevation Collection Settings
    USGS_ELEVATION_SAMPLE_DISTANCE_M: float = 50.0  # Sample every 50 meters
    USGS_ELEVATION_API_TIMEOUT: int = 10  # 10 second timeout
    USGS_ELEVATION_RATE_LIMIT_DELAY: float = 1.0  # 1 second delay between requests
    USGS_ELEVATION_ERROR_THRESHOLD: float = 0.1  # 10% failure rate threshold
    USGS_ELEVATION_LOG_FILE: str = "logs/usgs_elevation_collector.log"

    # Trail Matching Settings
    TRAIL_MATCHING_DISTANCE_THRESHOLD_M: float = (
        100.0  # Maximum distance for trail matching
    )
    TRAIL_MATCHING_CONFIDENCE_THRESHOLD: float = (
        0.7  # Minimum confidence score for matches
    )
    TRAIL_MATCHING_NAME_WEIGHT: float = (
        0.6  # Weight for name similarity in confidence calculation
    )
    TRAIL_MATCHING_DISTANCE_WEIGHT: float = (
        0.4  # Weight for distance in confidence calculation
    )
    TRAIL_MATCHING_LOG_FILE: str = "logs/trail_matcher.log"
    TRAIL_MATCHING_OUTPUT_GPKG: str = "artifacts/gmaps_hiking_locations_matched.gpkg"

    # Orchestration Settings
    ORCHESTRATOR_LOG_FILE: str = "logs/orchestrator.log"
    ORCHESTRATOR_STEP_TIMEOUT: int = 3600  # 1 hour max per step
    ORCHESTRATOR_ELEVATION_TIMEOUT: int = 86400  # 24 hours for elevation collection

    # Logging Configuration
    LOG_LEVEL: str = "INFO"
    LOG_MAX_BYTES: int = 5 * 1024 * 1024  # 5MB
    LOG_BACKUP_COUNT: int = 3

    def __init__(self):
        """Initialize configuration by loading from environment variables."""
        self._load_from_env()
        # Removed global validation - now done contextually

    def _load_from_env(self):
        """Load configuration values from environment variables."""
        # API settings
        api_key = os.getenv("NPS_API_KEY")
        if api_key:
            self.API_KEY = api_key

        user_email = os.getenv("NPS_USER_EMAIL")
        if user_email:
            self.USER_EMAIL = user_email

        # Database settings
        db_host = os.getenv("POSTGRES_HOST")
        if db_host:
            self.DB_HOST = db_host

        db_port = os.getenv("POSTGRES_PORT")
        if db_port:
            self.DB_PORT = int(db_port)

        db_name = os.getenv("POSTGRES_DB")
        if db_name:
            self.DB_NAME = db_name

        db_user = os.getenv("POSTGRES_USER")
        if db_user:
            self.DB_USER = db_user

        db_password = os.getenv("POSTGRES_PASSWORD")
        if db_password:
            self.DB_PASSWORD = db_password

        db_sslmode = os.getenv("POSTGRES_SSLMODE")
        if db_sslmode:
            self.DB_SSLMODE = db_sslmode

        # Optional overrides
        api_base_url = os.getenv("API_BASE_URL")
        if api_base_url:
            self.API_BASE_URL = api_base_url

        request_timeout = os.getenv("REQUEST_TIMEOUT")
        if request_timeout:
            self.REQUEST_TIMEOUT = int(request_timeout)

        default_delay = os.getenv("DEFAULT_DELAY_SECONDS")
        if default_delay:
            self.DEFAULT_DELAY_SECONDS = float(default_delay)

        log_level = os.getenv("LOG_LEVEL")
        if log_level:
            self.LOG_LEVEL = log_level

    def validate_for_api_operations(self):
        """
        Validate requirements for API-only operations (CSV output).

        Raises:
            ValueError: If required configuration for API operations is missing.
        """
        if not self.API_KEY:
            raise ValueError(
                "NPS_API_KEY environment variable is required for API operations. "
                "Please set it in your .env file or environment."
            )

    def validate_for_database_operations(self):
        """
        Validate requirements for database operations (profiling, OSM collection, etc).

        Raises:
            ValueError: If required configuration for database operations is missing.
        """
        if not self.DB_PASSWORD:
            raise ValueError(
                "POSTGRES_PASSWORD environment variable is required for database operations. "
                "Please set it in your .env file or environment."
            )

    def validate_for_api_and_database_operations(self):
        """
        Validate requirements for API collection with database storage (--write-db flag).

        Raises:
            ValueError: If required configuration for API + database operations is missing.
        """
        self.validate_for_api_operations()
        self.validate_for_database_operations()

    def get_database_url(self) -> str:
        """
        Generate database connection URL.

        Returns:
            str: PostgreSQL connection URL
        """
        url = f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        if self.DB_SSLMODE:
            url += f"?sslmode={self.DB_SSLMODE}"
        return url


# Global configuration instance
config = Config()

"""
Configuration settings for the NPS Hikes project.

This module centralizes all configuration values and provides a single source of truth for all
configurable parameters.
"""

import os
from typing import Optional


class Config:
    """
    Central configuration class for the NPS Hikes project.

    This class consolidates all configuration values including API settings,
    database connections, file paths, and processing parameters.
    """

    # API Configuration
    API_BASE_URL: str = "https://developer.nps.gov/api/v1"
    API_KEY: Optional[str] = None
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

    # Database Configuration
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "nps_data"
    DB_USER: str = "postgres"
    DB_PASSWORD: Optional[str] = None

    # File Paths
    DEFAULT_INPUT_CSV: str = "parks.csv"
    DEFAULT_OUTPUT_CSV: str = "park_data_collected.csv"
    DEFAULT_OUTPUT_GPKG: str = "park_boundaries_collected.gpkg"
    LOG_FILE: str = "nps_collector.log"

    # Logging Configuration
    LOG_LEVEL: str = "INFO"
    LOG_MAX_BYTES: int = 5 * 1024 * 1024  # 5MB
    LOG_BACKUP_COUNT: int = 3

    def __init__(self):
        """Initialize configuration by loading from environment variables."""
        self._load_from_env()
        self._validate()

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

    def _validate(self):
        """
        Validate required configuration values.

        Raises:
            ValueError: If required configuration is missing.
        """
        if not self.API_KEY:
            raise ValueError(
                "NPS_API_KEY environment variable is required. "
                "Please set it in your .env file or environment."
            )

        if not self.DB_PASSWORD:
            raise ValueError(
                "POSTGRES_PASSWORD environment variable is required. "
                "Please set it in your .env file or environment."
            )

    def get_database_url(self) -> str:
        """
        Generate database connection URL.

        Returns:
            str: PostgreSQL connection URL
        """
        return f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    def get_database_config(self) -> dict:
        """
        Get database configuration as a dictionary.

        Returns:
            dict: Database configuration parameters
        """
        return {
            "POSTGRES_HOST": self.DB_HOST,
            "POSTGRES_PORT": self.DB_PORT,
            "POSTGRES_DB": self.DB_NAME,
            "POSTGRES_USER": self.DB_USER,
            "POSTGRES_PASSWORD": self.DB_PASSWORD,
        }


# Global configuration instance
config = Config()

"""
Database connection utilities for the API.

Reuses the existing project configuration for database access.
"""

import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

# Add parent directory to path to import project modules
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from config.settings import Config

# Global engine instance (created once, reused)
_engine = None


def get_db_engine() -> Engine:
    """
    Get or create a SQLAlchemy engine for database connections.

    Uses the existing Config class from the project for database credentials.
    The engine is created once and reused across requests.

    Returns:
        SQLAlchemy Engine instance
    """
    global _engine

    if _engine is None:
        # Build PostgreSQL connection string from Config
        db_url = (
            f"postgresql://{Config.DB_USER}:{Config.DB_PASSWORD}"
            f"@{Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}"
        )

        # Create engine with connection pooling
        # pool_pre_ping=True checks if connections are alive before using them
        _engine = create_engine(db_url, pool_pre_ping=True)

    return _engine

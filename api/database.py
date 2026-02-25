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

from config.settings import config

# Global engine instance (created once, reused)
_engine = None


def get_db_engine() -> Engine:
    """
    Get or create a SQLAlchemy engine for database connections.

    Uses the existing config instance from the project for database credentials.
    The engine is created once and reused across requests.

    Returns:
        SQLAlchemy Engine instance
    """
    global _engine

    if _engine is None:
        # Build PostgreSQL connection string from config
        db_url = (
            f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}"
            f"@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
        )
        if config.DB_SSLMODE:
            db_url += f"?sslmode={config.DB_SSLMODE}"

        # Create engine with connection pooling
        # pool_pre_ping=True checks if connections are alive before using them
        _engine = create_engine(db_url, pool_pre_ping=True)

    return _engine

#!/usr/bin/env python3
"""
Database Reset Script

This script provides a clean way to drop all existing tables and recreate them
with the new standardized schema. Use this when you want to start fresh with
the new schema structure.

Usage:
    python reset_database.py

This will:
1. Drop all existing tables and sequences
2. Create all tables using the new SQL schema files
3. Log the entire process for verification
"""

import logging
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from scripts.database.db_writer import DatabaseWriter, get_postgres_engine
from sqlalchemy import text


def setup_logging():
    """Set up logging for the reset process."""
    from utils.logging import setup_logging as setup_centralized_logging

    return setup_centralized_logging(
        log_level="INFO",
        log_file="logs/database_reset.log",
        logger_name="database_reset",
    )


def main():
    """Main function to reset the database."""
    logger = setup_logging()

    try:
        logger.info("Starting database reset process...")

        # Create database engine and writer
        engine = get_postgres_engine()
        writer = DatabaseWriter(engine, logger)

        logger.info("Step 1: Dropping all existing tables and sequences...")
        writer.drop_all_tables()

        logger.info("Step 2: Creating all tables with new standardized schema...")
        writer._create_all_tables()

        logger.info("✅ Database reset completed successfully!")
        logger.info("All tables have been recreated with the new standardized schema.")

        # Verify tables were created
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    """
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public'
                AND tablename NOT IN (
                    'spatial_ref_sys', 'geometry_columns', 'geography_columns',
                    'raster_columns', 'raster_overviews'
                )
                ORDER BY tablename
            """
                )
            )
            tables = [row[0] for row in result]

            logger.info(f"Created tables: {', '.join(tables)}")

            if len(tables) == 7:
                logger.info("✅ All expected tables were created successfully!")
            else:
                logger.warning(f"⚠️  Expected 7 tables, but found {len(tables)}")

    except Exception as e:
        logger.error(f"❌ Database reset failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

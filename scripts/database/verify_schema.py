#!/usr/bin/env python3
"""
Schema Verification Script

This script verifies that the updated database schema has been applied correctly
with standardized data types and constraints.

Usage:
    python scripts/database/verify_schema.py

This will:
1. Connect to the database
2. Verify all tables exist with correct column types
3. Check that constraints are properly applied
4. Validate coordinate precision and trail length precision
5. Report any issues found
"""

import logging
import os
import sys
from typing import Any, Dict, List

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from scripts.database.db_writer import get_postgres_engine


def setup_logging():
    """Set up logging for the verification process."""
    from utils.logging import setup_logging as setup_centralized_logging

    return setup_centralized_logging(
        log_level="INFO",
        log_file="logs/schema_verification.log",
        logger_name="schema_verification",
    )


def verify_coordinate_precision(engine, logger) -> bool:
    """Verify that coordinate columns have standardized precision."""
    logger.info("🔍 Verifying coordinate precision...")

    coordinate_tables = [
        ("parks", ["latitude", "longitude"]),
        ("gmaps_hiking_locations", ["latitude", "longitude"]),
        ("gmaps_hiking_locations_matched", ["latitude", "longitude"]),
    ]

    all_correct = True

    for table_name, coord_columns in coordinate_tables:
        try:
            with engine.connect() as conn:
                for col_name in coord_columns:
                    result = conn.execute(
                        text(
                            f"""
                        SELECT data_type, numeric_precision, numeric_scale
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                            AND table_name = '{table_name}'
                            AND column_name = '{col_name}'
                    """
                        )
                    )

                    row = result.fetchone()
                    if row:
                        data_type, precision, scale = row
                        if col_name == "latitude":
                            expected_precision, expected_scale = 10, 8
                        else:  # longitude
                            expected_precision, expected_scale = 11, 8

                        if precision == expected_precision and scale == expected_scale:
                            logger.info(
                                f"✅ {table_name}.{col_name}: DECIMAL({precision},{scale}) - Correct"
                            )
                        else:
                            logger.error(
                                f"❌ {table_name}.{col_name}: DECIMAL({precision},{scale}) - Expected DECIMAL({expected_precision},{expected_scale})"
                            )
                            all_correct = False
                    else:
                        logger.error(f"❌ Column {table_name}.{col_name} not found")
                        all_correct = False

        except Exception as e:
            logger.error(f"❌ Error checking {table_name}: {e}")
            all_correct = False

    return all_correct


def verify_trail_length_precision(engine, logger) -> bool:
    """Verify that trail length columns have standardized precision."""
    logger.info("🔍 Verifying trail length precision...")

    length_tables = [
        ("osm_hikes", "length_miles"),
        ("tnm_hikes", "length_miles"),
    ]

    all_correct = True

    for table_name, col_name in length_tables:
        try:
            with engine.connect() as conn:
                result = conn.execute(
                    text(
                        f"""
                    SELECT data_type, numeric_precision, numeric_scale
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                        AND table_name = '{table_name}'
                        AND column_name = '{col_name}'
                """
                    )
                )

                row = result.fetchone()
                if row:
                    data_type, precision, scale = row
                    expected_precision, expected_scale = 8, 3

                    if precision == expected_precision and scale == expected_scale:
                        logger.info(
                            f"✅ {table_name}.{col_name}: DECIMAL({precision},{scale}) - Correct"
                        )
                    else:
                        logger.error(
                            f"❌ {table_name}.{col_name}: DECIMAL({precision},{scale}) - Expected DECIMAL({expected_precision},{expected_scale})"
                        )
                        all_correct = False
                else:
                    logger.error(f"❌ Column {table_name}.{col_name} not found")
                    all_correct = False

        except Exception as e:
            logger.error(f"❌ Error checking {table_name}: {e}")
            all_correct = False

    return all_correct


def verify_constraints(engine, logger) -> bool:
    """Verify that validation constraints are properly applied."""
    logger.info("🔍 Verifying validation constraints...")

    constraints_to_check = [
        ("parks", "chk_parks_latitude"),
        ("parks", "chk_parks_longitude"),
        ("gmaps_hiking_locations", "chk_gmaps_latitude"),
        ("gmaps_hiking_locations", "chk_gmaps_longitude"),
        ("gmaps_hiking_locations_matched", "chk_matched_latitude"),
        ("gmaps_hiking_locations_matched", "chk_matched_longitude"),
        ("gmaps_hiking_locations_matched", "chk_confidence_score"),
        ("gmaps_hiking_locations_matched", "chk_similarity_score"),
        ("osm_hikes", "chk_osm_length"),
        ("tnm_hikes", "chk_tnm_length"),
    ]

    all_correct = True

    try:
        with engine.connect() as conn:
            for table_name, constraint_name in constraints_to_check:
                result = conn.execute(
                    text(
                        f"""
                    SELECT conname
                    FROM pg_constraint
                    WHERE conrelid = '{table_name}'::regclass
                        AND conname = '{constraint_name}'
                """
                    )
                )

                if result.fetchone():
                    logger.info(f"✅ {table_name}.{constraint_name} - Found")
                else:
                    logger.error(f"❌ {table_name}.{constraint_name} - Missing")
                    all_correct = False

    except Exception as e:
        logger.error(f"❌ Error checking constraints: {e}")
        all_correct = False

    return all_correct


def verify_indexes(engine, logger) -> bool:
    """Verify that indexes are properly created."""
    logger.info("🔍 Verifying indexes...")

    indexes_to_check = [
        ("osm_hikes", "idx_osm_hikes_length_miles"),
        ("tnm_hikes", "idx_tnm_hikes_length_miles"),
    ]

    all_correct = True

    try:
        with engine.connect() as conn:
            for table_name, index_name in indexes_to_check:
                result = conn.execute(
                    text(
                        f"""
                    SELECT indexname
                    FROM pg_indexes
                    WHERE tablename = '{table_name}'
                        AND indexname = '{index_name}'
                """
                    )
                )

                if result.fetchone():
                    logger.info(f"✅ {table_name}.{index_name} - Found")
                else:
                    logger.error(f"❌ {table_name}.{index_name} - Missing")
                    all_correct = False

    except Exception as e:
        logger.error(f"❌ Error checking indexes: {e}")
        all_correct = False

    return all_correct


def verify_table_structure(engine, logger) -> bool:
    """Verify that all expected tables exist."""
    logger.info("🔍 Verifying table structure...")

    expected_tables = [
        "parks",
        "park_boundaries",
        "osm_hikes",
        "tnm_hikes",
        "gmaps_hiking_locations",
        "gmaps_hiking_locations_matched",
        "usgs_trail_elevations",
    ]

    all_correct = True

    try:
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        # Filter out PostGIS system tables
        postgis_system_tables = {
            "spatial_ref_sys",
            "geometry_columns",
            "geography_columns",
            "raster_columns",
            "raster_overviews",
        }
        user_tables = [t for t in existing_tables if t not in postgis_system_tables]

        for table_name in expected_tables:
            if table_name in user_tables:
                logger.info(f"✅ Table {table_name} - Found")
            else:
                logger.error(f"❌ Table {table_name} - Missing")
                all_correct = False

    except Exception as e:
        logger.error(f"❌ Error checking tables: {e}")
        all_correct = False

    return all_correct


def main():
    """Main function to verify the schema."""
    logger = setup_logging()

    try:
        logger.info("🚀 Starting schema verification...")

        # Create database engine
        engine = get_postgres_engine()

        # Run all verification checks
        checks = [
            ("Table Structure", verify_table_structure),
            ("Coordinate Precision", verify_coordinate_precision),
            ("Trail Length Precision", verify_trail_length_precision),
            ("Validation Constraints", verify_constraints),
            ("Indexes", verify_indexes),
        ]

        all_passed = True

        for check_name, check_func in checks:
            logger.info(f"\n📋 Running {check_name} check...")
            if not check_func(engine, logger):
                all_passed = False
                logger.error(f"❌ {check_name} check failed")
            else:
                logger.info(f"✅ {check_name} check passed")

        # Final summary
        logger.info("\n" + "=" * 60)
        if all_passed:
            logger.info("🎉 ALL CHECKS PASSED! Schema verification successful!")
            logger.info(
                "✅ Database schema has been successfully updated with standardized data types"
            )
        else:
            logger.error("❌ SOME CHECKS FAILED! Please review the errors above")
            sys.exit(1)

    except Exception as e:
        logger.error(f"❌ Schema verification failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

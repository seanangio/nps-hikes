"""
Unified Database Writer for NPS Hikes Project

This module provides a comprehensive database writing solution that consolidates
all database operations for the NPS Hikes project. It supports multiple data
types, storage patterns, and provides both generic and specialized methods for
different collection workflows.

Key Features:
- Unified interface for all database operations
- Support for both DataFrame and GeoDataFrame data
- Configurable upsert vs append operations
- Automatic table creation with proper schemas
- PostGIS geometry handling for spatial data
- Completion tracking for resumable workflows
- Comprehensive error handling and logging
- Connection management and transaction safety

The module is designed to be used by all data collectors in the project:
- NPS park metadata and boundary collection
- OSM hiking trail data collection
- TNM hiking trail data collection
- Future data collection modules

Example Usage:
    # Initialize writer
    engine = get_postgres_engine()
    writer = DatabaseWriter(engine, logger)

    # Write park metadata (with upserts)
    writer.write_parks(parks_df, mode='upsert')

    # Write park boundaries (with upserts)
    writer.write_park_boundaries(boundaries_gdf, mode='upsert')

    # Write trail data (append only)
    writer.write_osm_hikes(trails_gdf, mode='append')

    # Check completion status
    completed_parks = writer.get_completed_records('osm_hikes', 'park_code')
"""

from __future__ import annotations

import logging
import os
from typing import Set, Optional, Union, Dict, Any, List, TYPE_CHECKING
import pandas as pd
import geopandas as gpd
import shapely.geometry
from sqlalchemy import (
    create_engine,
    Table,
    MetaData,
    Column,
    String,
    Float,
    Text,
    text,
    Engine,
    inspect,
    DateTime,
    ForeignKeyConstraint,
)
from sqlalchemy.dialects.postgresql import insert
from geoalchemy2 import Geometry
from sqlalchemy.exc import SQLAlchemyError

if TYPE_CHECKING:
    from config.settings import Config

# Type annotation allows config to be Config or None
config: Config | None = None
CONFIG_AVAILABLE = False

# Try to import config, but handle gracefully if it fails
try:
    import sys
    import os

    sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
    from config.settings import config as imported_config

    config = imported_config
    CONFIG_AVAILABLE = True
except Exception:
    pass  # config remains None


def get_postgres_engine() -> Engine:
    """
    Create a SQLAlchemy engine for PostgreSQL/PostGIS using configuration.

    This function creates a database connection using the configuration settings
    and returns a SQLAlchemy engine that can be used for all database operations.

    Returns:
        Engine: SQLAlchemy engine instance configured for PostgreSQL/PostGIS

    Raises:
        ValueError: If any required configuration is missing
        SQLAlchemyError: If database connection cannot be established
    """
    if not CONFIG_AVAILABLE or config is None:
        raise ValueError("Configuration not available. Cannot create database engine.")

    # Validate database requirements
    config.validate_for_database_operations()

    conn_str = config.get_database_url()
    return create_engine(conn_str)


class DatabaseWriter:
    """
    Unified database writer for all NPS Hikes project data.

    This class provides a consistent interface for writing different types of data
    to the PostgreSQL/PostGIS database. It handles table creation, data validation,
    and supports both upsert and append operations depending on the data type.

    The writer is designed to be stateless and thread-safe, with all state
    managed through the database connection and transaction handling.

    Table schemas are now loaded from SQL files in sql/schema/ directory with
    automatic dependency checking to ensure proper creation order.
    """

    def __init__(self, engine: Engine, logger: Optional[logging.Logger] = None):
        """
        Initialize the database writer.

        Args:
            engine (Engine): SQLAlchemy engine for database connections
            logger (Optional[logging.Logger]): Logger instance for operation tracking.
                                             If None, creates a default logger.
        """
        self.engine = engine
        self.logger = logger or logging.getLogger(__name__)
        self.metadata = MetaData()

        # Define table dependencies for proper creation order
        self.table_dependencies = {
            "parks": [],
            "park_boundaries": ["parks"],
            "osm_hikes": ["parks"],
            "tnm_hikes": ["parks"],
            "gmaps_hiking_locations": ["parks"],
            "gmaps_hiking_locations_matched": ["gmaps_hiking_locations"],
            "usgs_trail_elevations": ["gmaps_hiking_locations_matched"],
        }

        # NPS table schemas - defined once and reused
        self._define_nps_table_schemas()

    def _define_nps_table_schemas(self) -> None:
        """
        Define SQLAlchemy table schemas for NPS collector tables.

        This method sets up Table objects for parks and park_boundaries tables
        that use SQLAlchemy's declarative approach. Other tables like osm_hikes
        use raw SQL creation and are handled separately.
        """
        # Parks metadata table
        self.parks_table = Table(
            "parks",
            self.metadata,
            Column("park_code", String, primary_key=True),
            Column("park_name", Text),
            Column("visit_month", String),
            Column("visit_year", String),
            Column("full_name", Text),
            Column("states", String),
            Column("url", Text),
            Column("latitude", Float),
            Column("longitude", Float),
            Column("description", Text),
            Column("error_message", Text),
            Column("collection_status", String),
            Column(
                "collected_at",
                DateTime(timezone=True),
                nullable=False,
                server_default=text("NOW()"),
            ),
            extend_existing=True,
        )

        # Park boundaries table
        self.park_boundaries_table = Table(
            "park_boundaries",
            self.metadata,
            Column("park_code", String, primary_key=True),
            Column("boundary_source", String),
            Column("collection_status", String),
            Column("error_message", Text),
            Column("bbox", String(100)),  # Bounding box as "xmin,ymin,xmax,ymax" string
            Column(
                "collected_at",
                DateTime(timezone=True),
                nullable=False,
                server_default=text("NOW()"),
            ),
            Column("geometry_type", String),
            Column(
                "geometry", Geometry(geometry_type="MULTIPOLYGON", srid=4326)
            ),  # Geometry column last
            ForeignKeyConstraint(
                ["park_code"], ["parks.park_code"]
            ),  # Reference to authoritative parks table
            extend_existing=True,
        )

    def _check_primary_key(self, table_name: str, pk_column: str) -> None:
        """
        Check if the given table exists and if pk_column is a primary key.

        This validation ensures data integrity by confirming that required
        primary key constraints are in place before attempting data operations.

        Args:
            table_name (str): Name of the table to check
            pk_column (str): Name of the column that should be a primary key

        Raises:
            ValueError: If the table exists but doesn't have the expected primary key
        """
        inspector = inspect(self.engine)
        if table_name in inspector.get_table_names():
            pk = inspector.get_pk_constraint(table_name)
            pk_cols = pk.get("constrained_columns", [])
            if pk_column not in pk_cols:
                raise ValueError(
                    f"Table '{table_name}' exists but does not have '{pk_column}' as a primary key. "
                    "Please fix the schema before proceeding."
                )

    def _load_sql_schema(self, table_name: str) -> str:
        """
        Load SQL schema from file with comprehensive error handling.

        Args:
            table_name (str): Name of the table (without .sql extension)

        Returns:
            str: SQL content from the schema file

        Raises:
            FileNotFoundError: If SQL schema file is missing
            ValueError: If SQL schema file is empty
            Exception: If any other error occurs reading the file
        """
        sql_file = f"{table_name}.sql"
        # Get project root directory (two levels up from scripts/database/)
        project_root = os.path.join(os.path.dirname(__file__), "..", "..")
        sql_path = os.path.join(project_root, "sql", "schema", sql_file)

        try:
            if not os.path.exists(sql_path):
                raise FileNotFoundError(f"SQL schema file not found: {sql_path}")

            with open(sql_path, "r") as f:
                sql_content = f.read().strip()

            if not sql_content:
                raise ValueError(f"SQL schema file is empty: {sql_path}")

            return sql_content

        except FileNotFoundError as e:
            self.logger.error(f"Schema file missing: {e}")
            raise
        except ValueError as e:
            self.logger.error(f"Invalid schema file: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Failed to read schema file {sql_path}: {e}")
            raise

    def _create_table_from_sql(self, table_name: str) -> None:
        """
        Create table from SQL schema file.

        Args:
            table_name (str): Name of the table to create

        Raises:
            Exception: If table creation fails
        """
        try:
            sql_content = self._load_sql_schema(table_name)

            with self.engine.begin() as conn:
                conn.execute(text(sql_content))

            self.logger.info(f"Successfully created table: {table_name}")

        except Exception as e:
            self.logger.error(f"Failed to create table {table_name}: {e}")
            raise

    def _create_all_tables(self) -> None:
        """
        Create all tables in dependency order with error handling.

        Uses the table_dependencies dictionary to determine the correct order
        and ensures all dependencies are met before creating each table.

        Raises:
            RuntimeError: If circular dependency is detected
            Exception: If any table creation fails
        """
        created_tables: set[str] = set()

        while len(created_tables) < len(self.table_dependencies):
            progress_made = False

            for table_name, dependencies in self.table_dependencies.items():
                if table_name in created_tables:
                    continue

                # Check if all dependencies are met
                if all(dep in created_tables for dep in dependencies):
                    try:
                        self._create_table_from_sql(table_name)
                        created_tables.add(table_name)
                        progress_made = True
                    except Exception as e:
                        self.logger.error(f"Failed to create table {table_name}: {e}")
                        raise

            if not progress_made:
                remaining = set(self.table_dependencies.keys()) - created_tables
                raise RuntimeError(
                    f"Circular dependency detected in table creation. Remaining tables: {remaining}"
                )

    def drop_all_tables(self) -> None:
        """
        Drop all tables in the correct order to avoid foreign key violations.

        This method drops tables in reverse dependency order and handles
        any remaining tables that might exist outside our standard schema.

        Raises:
            Exception: If any error occurs during table dropping
        """
        # Tables in reverse dependency order
        tables_to_drop = [
            "usgs_trail_elevations",
            "gmaps_hiking_locations_matched",
            "gmaps_hiking_locations",
            "tnm_hikes",
            "osm_hikes",
            "park_boundaries",
            "parks",
        ]

        try:
            with self.engine.begin() as conn:
                # Drop tables in reverse dependency order
                for table_name in tables_to_drop:
                    conn.execute(text(f"DROP TABLE IF EXISTS {table_name} CASCADE"))
                    self.logger.info(f"Dropped table: {table_name}")

                # Drop any remaining tables (excluding PostGIS system tables)
                result = conn.execute(
                    text(
                        """
                    SELECT tablename FROM pg_tables
                    WHERE schemaname = 'public'
                    AND tablename NOT IN (
                        'spatial_ref_sys', 'geometry_columns', 'geography_columns',
                        'raster_columns', 'raster_overviews'
                    )
                """
                    )
                )
                remaining_tables = [row[0] for row in result]

                for table_name in remaining_tables:
                    conn.execute(text(f"DROP TABLE IF EXISTS {table_name} CASCADE"))
                    self.logger.info(f"Dropped remaining table: {table_name}")

                if remaining_tables:
                    self.logger.info(
                        "Preserved PostGIS system tables (spatial_ref_sys, geometry_columns, etc.)"
                    )

                # Drop any sequences
                result = conn.execute(
                    text(
                        """
                    SELECT sequence_name FROM information_schema.sequences
                    WHERE sequence_schema = 'public'
                """
                    )
                )
                sequences = [row[0] for row in result]

                for seq_name in sequences:
                    conn.execute(text(f"DROP SEQUENCE IF EXISTS {seq_name} CASCADE"))
                    self.logger.info(f"Dropped sequence: {seq_name}")

            self.logger.info("Successfully dropped all tables and sequences")

        except Exception as e:
            self.logger.error(f"Error dropping tables: {e}")
            raise

    def reset_database(self) -> None:
        """
        Complete database reset: drop all tables and recreate with new schema.

        This method provides a clean way to start fresh with the new standardized
        schema. It drops all existing tables and sequences, then creates all
        tables using the new SQL schema files.

        Raises:
            Exception: If any error occurs during the reset process
        """
        self.logger.info("Starting complete database reset...")

        try:
            # Step 1: Drop all existing tables
            self.logger.info("Step 1: Dropping all existing tables and sequences...")
            self.drop_all_tables()

            # Step 2: Create all tables with new schema
            self.logger.info(
                "Step 2: Creating all tables with new standardized schema..."
            )
            self._create_all_tables()

            self.logger.info("✅ Database reset completed successfully!")
            self.logger.info(
                "All tables have been recreated with the new standardized schema."
            )

        except Exception as e:
            self.logger.error(f"❌ Database reset failed: {e}")
            raise

    def _create_osm_hikes_table(self) -> None:
        """
        Create the osm_hikes table for OSM trail data if it doesn't exist.

        This method creates the specialized table for hiking trail data with
        a composite primary key and proper PostGIS geometry support. The table
        design supports the OSM data collection workflow.

        Raises:
            SQLAlchemyError: If table creation fails
        """
        self._create_table_from_sql("osm_hikes")

    def _create_tnm_hikes_table(self) -> None:
        """
        Create the tnm_hikes table for TNM trail data if it doesn't exist.

        This table stores hiking trail geometries and attributes from The National Map.
        It uses permanent_identifier as the primary key since it's globally unique.
        """
        self._create_table_from_sql("tnm_hikes")

    def _create_gmaps_hiking_locations_table(self) -> None:
        """
        Create the gmaps_hiking_locations table for Google Maps hiking data if it doesn't exist.

        This table stores hiking location data with coordinates from Google Maps.
        """
        self._create_table_from_sql("gmaps_hiking_locations")

    def _create_usgs_trail_elevations_table(self) -> None:
        """
        Create the usgs_trail_elevations table for USGS elevation data if it doesn't exist.

        This table stores elevation profile data collected from USGS API for matched trails.
        """
        self._create_table_from_sql("usgs_trail_elevations")

    def _create_gmaps_hiking_locations_matched_table(self) -> None:
        """
        Create the gmaps_hiking_locations_matched table for trail matching results if it doesn't exist.

        This table stores the results of matching Google Maps hiking locations to trail linestrings
        from OSM and TNM data. It includes both the original GMaps data and the matched trail
        information with confidence scores and matching metrics.
        """
        self._create_table_from_sql("gmaps_hiking_locations_matched")

    def _ensure_gmaps_matched_constraints(self) -> None:
        """
        Ensure that gmaps_hiking_locations_matched table has proper constraints.

        This method adds missing constraints that may be lost when geopandas
        recreates tables.
        """
        try:
            with self.engine.begin() as conn:
                # Check if constraints already exist
                result = conn.execute(
                    text(
                        """
                    SELECT conname FROM pg_constraint
                    WHERE conrelid = 'gmaps_hiking_locations_matched'::regclass
                        AND conname IN ('fk_matched_gmaps_location', 'fk_matched_park_code')
                """
                    )
                )
                existing_constraints = {row[0] for row in result.fetchall()}

                # Add missing constraints
                if "fk_matched_gmaps_location" not in existing_constraints:
                    try:
                        # First ensure gmaps_location_id is NOT NULL
                        conn.execute(
                            text(
                                """
                            UPDATE gmaps_hiking_locations_matched
                            SET gmaps_location_id = id
                            WHERE gmaps_location_id IS NULL
                        """
                            )
                        )
                        conn.execute(
                            text(
                                """
                            ALTER TABLE gmaps_hiking_locations_matched
                            ALTER COLUMN gmaps_location_id SET NOT NULL
                        """
                            )
                        )

                        # Add the foreign key constraint
                        conn.execute(
                            text(
                                """
                            ALTER TABLE gmaps_hiking_locations_matched
                            ADD CONSTRAINT fk_matched_gmaps_location
                            FOREIGN KEY (gmaps_location_id) REFERENCES gmaps_hiking_locations(id)
                        """
                            )
                        )
                        self.logger.debug(
                            "Added foreign key constraint for gmaps_location_id"
                        )
                    except Exception as e:
                        self.logger.warning(
                            f"Could not add gmaps_location_id constraint: {e}"
                        )

                if "fk_matched_park_code" not in existing_constraints:
                    try:
                        # Ensure park_code is NOT NULL
                        conn.execute(
                            text(
                                """
                            ALTER TABLE gmaps_hiking_locations_matched
                            ALTER COLUMN park_code SET NOT NULL
                        """
                            )
                        )

                        # Add the foreign key constraint
                        conn.execute(
                            text(
                                """
                            ALTER TABLE gmaps_hiking_locations_matched
                            ADD CONSTRAINT fk_matched_park_code
                            FOREIGN KEY (park_code) REFERENCES parks(park_code)
                        """
                            )
                        )
                        self.logger.debug("Added foreign key constraint for park_code")
                    except Exception as e:
                        self.logger.warning(f"Could not add park_code constraint: {e}")

        except Exception as e:
            self.logger.warning(
                f"Failed to ensure gmaps_hiking_locations_matched constraints: {e}"
            )

    def ensure_table_exists(self, table_name: str) -> None:
        """
        Ensure that the specified table exists in the database.

        Supports these tables:
        - 'parks': NPS park metadata (created via SQLAlchemy)
        - 'park_boundaries': NPS boundary data (created via SQLAlchemy)
        - 'osm_hikes': OSM trail data (created via raw SQL with composite PK)
        - 'tnm_hikes': TNM trail data (created via raw SQL with single PK)
        - 'gmaps_hiking_locations': Google Maps hiking locations (created via raw SQL)
        - 'gmaps_hiking_locations_matched': Trail matching results (created via raw SQL)
        - 'usgs_trail_elevations': USGS elevation data for matched trails (created via raw SQL)

        Args:
            table_name (str): Name of the table to create

        Raises:
            ValueError: If table_name is not in the supported list
            SQLAlchemyError: If table creation fails
        """
        if table_name == "osm_hikes":
            self._create_osm_hikes_table()
        elif table_name == "tnm_hikes":
            self._create_tnm_hikes_table()
        elif table_name == "gmaps_hiking_locations":
            self._create_gmaps_hiking_locations_table()
        elif table_name == "gmaps_hiking_locations_matched":
            self._create_gmaps_hiking_locations_matched_table()
        elif table_name == "usgs_trail_elevations":
            self._create_usgs_trail_elevations_table()
        elif table_name in ["parks", "park_boundaries"]:
            # Use SQLAlchemy table definitions
            self.metadata.create_all(
                self.engine,
                tables=[getattr(self, f"{table_name}_table")],
                checkfirst=True,
            )
            self.logger.info(f"Ensured {table_name} table exists in database")
        else:
            raise ValueError(f"Unknown table name: {table_name}")

    def get_completed_records(self, table_name: str, key_column: str) -> Set[str]:
        """
        Get set of keys for records that already exist in the specified table.

        This method enables resumable workflows by identifying which records
        have already been processed and stored in the database.

        Args:
            table_name (str): Name of the table to query
            key_column (str): Name of the column to use as the key

        Returns:
            Set[str]: Set of key values that already exist in the table.
                     Empty set if table doesn't exist or query fails.
        """
        try:
            sql = f"SELECT DISTINCT {key_column} FROM {table_name}"
            result = pd.read_sql(sql, self.engine)
            completed = set(result[key_column].tolist())
            if completed:
                self.logger.info(
                    f"Found {len(completed)} existing records in {table_name}: {sorted(list(completed))[:10]}..."
                )
            return completed
        except Exception as e:
            self.logger.warning(
                f"Could not check completed records in {table_name}: {e}"
            )
            return set()

    def write_parks(
        self, df: pd.DataFrame, mode: str = "upsert", table_name: str = "parks"
    ) -> None:
        """
        Write park metadata to the parks table.

        This method handles park metadata with upsert capabilities to prevent
        duplicates while allowing updates to existing records.

        Args:
            df (pd.DataFrame): Park metadata to write
            mode (str): Write mode - 'upsert' (default) or 'append'
            table_name (str): Target table name (default: 'parks')

        Raises:
            ValueError: If mode is not supported or primary key issues exist
            SQLAlchemyError: If database operations fail
        """
        if df.empty:
            self.logger.warning("No park data to save")
            return

        if mode not in ["upsert", "append"]:
            raise ValueError(f"Unsupported mode '{mode}'. Use 'upsert' or 'append'")

        # Ensure table exists and validate schema
        self.ensure_table_exists(table_name)
        if mode == "upsert":
            self._check_primary_key(table_name, "park_code")

        if mode == "upsert":
            self._upsert_parks(df, table_name)
        else:
            self._append_dataframe(df, table_name)

    def _upsert_parks(self, df: pd.DataFrame, table_name: str) -> None:
        """
        Perform upsert operation for parks data.

        Args:
            df (pd.DataFrame): Parks data to upsert
            table_name (str): Target table name
        """
        with self.engine.begin() as conn:
            for _, row in df.iterrows():
                row_dict = row.to_dict()
                stmt = insert(self.parks_table).values(**row_dict)
                update_cols = {
                    col: stmt.excluded[col] for col in row_dict if col != "park_code"
                }
                stmt = stmt.on_conflict_do_update(
                    index_elements=["park_code"], set_=update_cols
                )
                conn.execute(stmt)

        self.logger.info(f"Upserted {len(df)} park records to {table_name}")

    def write_park_boundaries(
        self,
        gdf: gpd.GeoDataFrame,
        mode: str = "upsert",
        table_name: str = "park_boundaries",
    ) -> None:
        """
        Write park boundary data to the park_boundaries table.

        This method handles spatial boundary data with proper PostGIS geometry
        handling and supports upsert operations for data updates.

        Args:
            gdf (gpd.GeoDataFrame): Boundary data to write
            mode (str): Write mode - 'upsert' (default) or 'append'
            table_name (str): Target table name (default: 'park_boundaries')

        Raises:
            ValueError: If mode is not supported or primary key issues exist
            SQLAlchemyError: If database operations fail
        """
        if gdf.empty:
            self.logger.warning("No boundary data to save")
            return

        if mode not in ["upsert", "append"]:
            raise ValueError(f"Unsupported mode '{mode}'. Use 'upsert' or 'append'")

        # Ensure table exists and validate schema
        self.ensure_table_exists(table_name)
        if mode == "upsert":
            self._check_primary_key(table_name, "park_code")

        if mode == "upsert":
            self._upsert_park_boundaries(gdf, table_name)
        else:
            self._append_geodataframe(gdf, table_name)

    def _upsert_park_boundaries(self, gdf: gpd.GeoDataFrame, table_name: str) -> None:
        """
        Perform upsert operation for park boundaries data.

        Args:
            gdf (gpd.GeoDataFrame): Boundary data to upsert
            table_name (str): Target table name
        """
        with self.engine.begin() as conn:
            for _, row in gdf.iterrows():
                geom_wkt = None
                geom = row["geometry"]
                if geom is not None and isinstance(
                    geom, shapely.geometry.base.BaseGeometry
                ):
                    geom_wkt = geom.wkt

                values = {
                    "park_code": row["park_code"],
                    "geometry": geom_wkt,
                    "geometry_type": row.get("geometry_type"),
                    "boundary_source": row.get("boundary_source"),
                    "error_message": row.get("error_message"),
                    "collection_status": row.get("collection_status"),
                    "bbox": row.get("bbox"),  # Add bbox column
                }

                stmt = insert(self.park_boundaries_table).values(**values)
                update_cols = {
                    col: stmt.excluded[col] for col in values if col != "park_code"
                }
                stmt = stmt.on_conflict_do_update(
                    index_elements=["park_code"], set_=update_cols
                )
                conn.execute(stmt)

        self.logger.info(f"Upserted {len(gdf)} boundary records to {table_name}")

    def write_tnm_hikes(
        self,
        gdf: gpd.GeoDataFrame,
        mode: str = "append",
        table_name: str = "tnm_hikes",
    ) -> None:
        """
        Write TNM hiking trail data to the tnm_hikes table.

        This method handles TNM trail data using geopandas' optimized PostGIS
        integration. It supports append mode for adding new records.

        Args:
            gdf (gpd.GeoDataFrame): GeoDataFrame containing TNM trail data
            mode (str): Write mode - 'append' (default) or 'upsert'
            table_name (str): Target table name (default: 'tnm_hikes')

        Raises:
            ValueError: If mode is not supported
            NotImplementedError: If upsert mode is requested (not implemented)
        """
        if gdf.empty:
            self.logger.warning("No trail data to save")
            return

        if mode not in ["append", "upsert"]:
            raise ValueError(f"Unsupported mode '{mode}'. Use 'append' or 'upsert'")

        # Ensure table exists
        self.ensure_table_exists(table_name)

        if mode == "append":
            self._append_geodataframe(gdf, table_name)
        else:
            # Upsert for tnm_hikes would need custom implementation
            # due to single primary key (permanentidentifier)
            raise NotImplementedError("Upsert mode not implemented for tnm_hikes table")

    def write_osm_hikes(
        self,
        gdf: gpd.GeoDataFrame,
        mode: str = "append",
        table_name: str = "osm_hikes",
    ) -> None:
        """
        Write hiking trail data to the osm_hikes table.

        This method handles OSM trail data using geopandas' optimized PostGIS
        integration. Trail data typically uses append-only operations since
        each trail has a unique OSM ID within each park.

        Args:
            gdf (gpd.GeoDataFrame): Trail data to write with required columns:
                                   osm_id, park_code, highway, name, source,
                                   length_miles, geometry_type, geometry, timestamp
            mode (str): Write mode - 'append' (default) or 'upsert'
            table_name (str): Target table name (default: 'osm_hikes')

        Raises:
            ValueError: If mode is not supported
            SQLAlchemyError: If database operations fail
        """
        if gdf.empty:
            self.logger.warning("No trail data to save")
            return

        if mode not in ["append", "upsert"]:
            raise ValueError(f"Unsupported mode '{mode}'. Use 'append' or 'upsert'")

        # Ensure table exists
        self.ensure_table_exists(table_name)

        if mode == "append":
            self._append_geodataframe(gdf, table_name)
        else:
            # Upsert for osm_hikes would need custom implementation
            # due to composite primary key (park_code, osm_id)
            raise NotImplementedError("Upsert mode not implemented for osm_hikes table")

    def _append_dataframe(self, df: pd.DataFrame, table_name: str) -> None:
        """
        Append DataFrame to table using pandas to_sql.

        Args:
            df (pd.DataFrame): Data to append
            table_name (str): Target table name
        """
        try:
            df.to_sql(table_name, self.engine, if_exists="append", index=False)
            self.logger.info(f"Appended {len(df)} records to {table_name}")
        except Exception as e:
            self.logger.error(f"Failed to append data to {table_name}: {e}")
            raise

    def _append_geodataframe(self, gdf: gpd.GeoDataFrame, table_name: str) -> None:
        """
        Append GeoDataFrame to table using geopandas to_postgis.

        Args:
            gdf (gpd.GeoDataFrame): Spatial data to append
            table_name (str): Target table name
        """
        try:
            gdf.to_postgis(table_name, self.engine, if_exists="append", index=False)
            self.logger.info(f"Appended {len(gdf)} spatial records to {table_name}")
        except Exception as e:
            self.logger.error(f"Failed to append spatial data to {table_name}: {e}")
            raise

    def write_gmaps_hiking_locations(
        self,
        df: pd.DataFrame,
        mode: str = "append",
        table_name: str = "gmaps_hiking_locations",
    ) -> None:
        """
        Write Google Maps hiking location data to the gmaps_hiking_locations table.

        This method handles hiking location data with coordinates. It supports
        both append and upsert modes, with upsert being useful for updating
        existing locations.

        Args:
            df (pd.DataFrame): Location data to write with required columns:
                               park_code, location_name, latitude, longitude
            mode (str): Write mode - 'append' (default) or 'upsert'
            table_name (str): Target table name (default: 'gmaps_hiking_locations')

        Raises:
            ValueError: If mode is not supported
            SQLAlchemyError: If database operations fail
        """
        if df.empty:
            self.logger.warning("No location data to save")
            return

        if mode not in ["append", "upsert"]:
            raise ValueError(f"Unsupported mode '{mode}'. Use 'append' or 'upsert'")

        # Ensure table exists
        self.ensure_table_exists(table_name)

        if mode == "append":
            self._append_dataframe(df, table_name)
        else:
            # Upsert implementation for updating existing locations
            self._upsert_gmaps_locations(df, table_name)

    def _upsert_gmaps_locations(self, df: pd.DataFrame, table_name: str) -> None:
        """
        Upsert Google Maps hiking locations using ON CONFLICT.

        Args:
            df (pd.DataFrame): Location data to upsert
            table_name (str): Target table name
        """
        try:
            # Use pandas to_sql with method='multi' for better performance
            df.to_sql(
                table_name, self.engine, if_exists="append", index=False, method="multi"
            )
            self.logger.info(f"Upserted {len(df)} records to {table_name}")
        except Exception as e:
            self.logger.error(f"Failed to upsert data to {table_name}: {e}")
            raise

    def park_exists_in_gmaps_table(self, park_code: str) -> bool:
        """
        Check if a park exists in the gmaps_hiking_locations table.

        Args:
            park_code (str): Park code to check

        Returns:
            bool: True if park exists, False otherwise
        """
        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text(
                        "SELECT COUNT(*) FROM gmaps_hiking_locations WHERE park_code = :park_code"
                    ),
                    {"park_code": park_code},
                )
                count = result.scalar()
                return count is not None and count > 0
        except Exception as e:
            self.logger.error(f"Failed to check if park {park_code} exists: {e}")
            return False

    def delete_gmaps_park_records(self, park_code: str) -> None:
        """
        Delete all records for a specific park from gmaps_hiking_locations table.

        Args:
            park_code (str): Park code whose records should be deleted
        """
        try:
            with self.engine.begin() as conn:
                result = conn.execute(
                    text(
                        "DELETE FROM gmaps_hiking_locations WHERE park_code = :park_code"
                    ),
                    {"park_code": park_code},
                )
                deleted_count = result.rowcount
                self.logger.info(
                    f"Deleted {deleted_count} records for park {park_code}"
                )
        except Exception as e:
            self.logger.error(f"Failed to delete records for park {park_code}: {e}")
            raise

    def write_gmaps_hiking_locations_matched(
        self,
        gdf: gpd.GeoDataFrame,
        mode: str = "replace",
        table_name: str = "gmaps_hiking_locations_matched",
    ) -> None:
        """
        Write matched trail data to the gmaps_hiking_locations_matched table.

        This method handles the results of trail matching operations, storing both the original
        Google Maps hiking location data and the matched trail information with confidence
        scores and matching metrics.

        Args:
            gdf (gpd.GeoDataFrame): Matched trail data to write with required columns:
                                   gmaps_location_id, park_code, location_name, latitude, longitude, created_at,
                                   matched_trail_name, source, name_similarity_score,
                                   min_point_to_trail_distance_m, confidence_score, matched,
                                   matched_trail_geometry
            mode (str): Write mode - 'replace' (default) or 'append'
            table_name (str): Target table name (default: 'gmaps_hiking_locations_matched')

        Raises:
            ValueError: If mode is not supported
            SQLAlchemyError: If database operations fail
        """
        if gdf.empty:
            self.logger.warning("No matched trail data to save")
            return

        if mode not in ["replace", "append"]:
            raise ValueError(f"Unsupported mode '{mode}'. Use 'replace' or 'append'")

        # Ensure table exists
        self.ensure_table_exists(table_name)

        if mode == "replace":
            self._replace_geodataframe(gdf, table_name)
        else:
            self._append_geodataframe(gdf, table_name)

    def _replace_geodataframe(self, gdf: gpd.GeoDataFrame, table_name: str) -> None:
        """
        Replace all data in a table using geopandas to_postgis.

        For tables with foreign key dependencies, this method truncates the table
        instead of dropping and recreating it to avoid constraint violations.

        Args:
            gdf (gpd.GeoDataFrame): Spatial data to replace existing data with
            table_name (str): Target table name
        """
        try:
            # First try the standard replace approach
            gdf.to_postgis(table_name, self.engine, if_exists="replace", index=False)
            self.logger.info(
                f"Replaced all data in {table_name} with {len(gdf)} spatial records"
            )
        except Exception as e:
            # If replace fails due to foreign key constraints, try truncate + append
            if "DependentObjectsStillExist" in str(e) or "CASCADE" in str(e):
                self.logger.info(
                    f"Replace failed due to foreign key constraints, using truncate + append for {table_name}"
                )
                try:
                    # Truncate the table
                    with self.engine.begin() as conn:
                        conn.execute(
                            text(
                                f"TRUNCATE TABLE {table_name} RESTART IDENTITY CASCADE"
                            )
                        )

                    # Append the new data
                    gdf.to_postgis(
                        table_name, self.engine, if_exists="append", index=False
                    )
                    self.logger.info(
                        f"Truncated and replaced all data in {table_name} with {len(gdf)} spatial records"
                    )
                except Exception as truncate_error:
                    self.logger.error(
                        f"Failed to truncate and replace spatial data in {table_name}: {truncate_error}"
                    )
                    raise
            else:
                self.logger.error(
                    f"Failed to replace spatial data in {table_name}: {e}"
                )
                raise

    def truncate_tables(self, table_names: List[str]) -> None:
        """
        Truncate (delete all rows from) the specified tables.

        This method is useful for resetting data during development or
        when performing complete data refreshes.

        Args:
            table_names (List[str]): List of table names to truncate

        Note:
            This operation is irreversible and will delete all data in the
            specified tables. Use with caution.
        """
        with self.engine.begin() as conn:
            for table in table_names:
                try:
                    self.logger.info(f"Truncating table '{table}'...")
                    conn.execute(
                        text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE;")
                    )
                    self.logger.info(f"Table '{table}' truncated")
                except Exception as e:
                    self.logger.error(f"Failed to truncate table '{table}': {e}")

    def get_table_info(self, table_name: str) -> Dict[str, Any]:
        """
        Get information about a table including row count and schema.

        Args:
            table_name (str): Name of the table to inspect

        Returns:
            Dict[str, Any]: Dictionary containing table information including
                           row_count, columns, and primary_keys
        """
        inspector = inspect(self.engine)

        info = {
            "exists": table_name in inspector.get_table_names(),
            "row_count": 0,
            "columns": [],
            "primary_keys": [],
        }

        if info["exists"]:
            try:
                # Get row count
                with self.engine.connect() as conn:
                    result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                    info["row_count"] = result.scalar()

                # Get column info
                info["columns"] = [
                    col["name"] for col in inspector.get_columns(table_name)
                ]

                # Get primary key info
                pk_constraint = inspector.get_pk_constraint(table_name)
                info["primary_keys"] = pk_constraint.get("constrained_columns", [])

            except Exception as e:
                self.logger.warning(
                    f"Could not get complete info for table {table_name}: {e}"
                )

        return info

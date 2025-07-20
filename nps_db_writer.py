"""
nps_db_writer.py

Database writing utilities for the NPS ETL pipeline.

This module provides functions to create a SQLAlchemy engine from environment variables
and to save park and boundary data to a PostgreSQL/PostGIS database.

To port to other backends (e.g., Snowflake, BigQuery), implement similar functions
with the appropriate SQLAlchemy connection string and save logic.
"""

import os
from sqlalchemy import create_engine, Table, MetaData, Column, String, Float, Text
from sqlalchemy.dialects.postgresql import insert
from geoalchemy2 import Geometry
from sqlalchemy.exc import SQLAlchemyError
import pandas as pd
import geopandas as gpd
import shapely.geometry

from config.settings import config


def get_postgres_engine():
    """
    Create a SQLAlchemy engine for PostgreSQL/PostGIS using configuration.
    Returns:
        sqlalchemy.engine.Engine: SQLAlchemy engine instance
    Raises:
        ValueError: If any required configuration is missing
    """
    # Use config values (which are already validated)
    conn_str = config.get_database_url()
    return create_engine(conn_str)


def _check_primary_key(engine, table_name, pk_column):
    """
    Check if the given table exists and if pk_column is a primary key.
    Raises a ValueError with a clear message if the PK is missing.
    """
    from sqlalchemy import inspect
    inspector = inspect(engine)
    if table_name in inspector.get_table_names():
        pk = inspector.get_pk_constraint(table_name)
        pk_cols = pk.get('constrained_columns', [])
        if pk_column not in pk_cols:
            raise ValueError(
                f"Table '{table_name}' exists but does not have '{pk_column}' as a primary key. "
                "Please fix the schema before proceeding."
            )


def save_park_results_to_db(df: pd.DataFrame, engine, table_name: str = "parks"):
    """
    Upsert park data (DataFrame) to a PostgreSQL table using ON CONFLICT DO UPDATE.
    Ensures 'park_code' is a primary key. Fails early with a clear error if not.
    Args:
        df (pd.DataFrame): Park data
        engine: SQLAlchemy engine
        table_name (str): Name of the table to write to (default 'parks')
    """
    _check_primary_key(engine, table_name, "park_code")
    metadata = MetaData()
    # Define table schema (ensure park_code is primary key)
    parks_table = Table(
        table_name,
        metadata,
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
        extend_existing=True,
    )
    metadata.create_all(engine, checkfirst=True)
    with engine.begin() as conn:
        for i, row in enumerate(df.to_dict(orient="records")):
            stmt = insert(parks_table).values(**row)
            update_cols = {col: stmt.excluded[col] for col in row if col != "park_code"}
            stmt = stmt.on_conflict_do_update(
                index_elements=["park_code"],
                set_=update_cols
            )
            result = conn.execute(stmt)
        print(f"✅ Park data upserted to table '{table_name}' in database.")


def save_boundary_results_to_db(
    gdf: gpd.GeoDataFrame, engine, table_name: str = "park_boundaries"
):
    """
    Upsert boundary data (GeoDataFrame) to a PostGIS table using ON CONFLICT DO UPDATE.
    Ensures 'park_code' is a primary key. Fails early with a clear error if not.
    Args:
        gdf (gpd.GeoDataFrame): Boundary data
        engine: SQLAlchemy engine
        table_name (str): Name of the table to write to (default 'park_boundaries')
    """
    _check_primary_key(engine, table_name, "park_code")
    metadata = MetaData()
    # Define table schema (ensure park_code is primary key)
    boundaries_table = Table(
        table_name,
        metadata,
        Column("park_code", String, primary_key=True),
        Column("geometry", Geometry(geometry_type="MULTIPOLYGON", srid=4326)),
        Column("geometry_type", String),
        Column("boundary_source", String),
        Column("error_message", Text),
        Column("collection_status", String),
        extend_existing=True,
    )
    metadata.create_all(engine, checkfirst=True)
    with engine.begin() as conn:
        for i, (_, row) in enumerate(gdf.iterrows()):
            geom_wkt = None
            geom = row["geometry"]
            if geom is not None and isinstance(geom, shapely.geometry.base.BaseGeometry):
                geom_wkt = geom.wkt
            values = {
                "park_code": row["park_code"],
                "geometry": geom_wkt,
                "geometry_type": row.get("geometry_type"),
                "boundary_source": row.get("boundary_source"),
                "error_message": row.get("error_message"),
                "collection_status": row.get("collection_status"),
            }
            stmt = insert(boundaries_table).values(**values)
            update_cols = {col: stmt.excluded[col] for col in values if col != "park_code"}
            stmt = stmt.on_conflict_do_update(
                index_elements=["park_code"],
                set_=update_cols
            )
            result = conn.execute(stmt)
        print(f"✅ Boundary data upserted to table '{table_name}' in database.")


def truncate_tables(engine, table_names):
    """
    Truncate (delete all rows from) the specified tables in the connected database.
    Args:
        engine: SQLAlchemy engine
        table_names (list of str): List of table names to truncate
    """
    from sqlalchemy import text
    with engine.begin() as conn:
        for table in table_names:
            try:
                print(f"Truncating table '{table}'...")
                conn.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE;"))
                print(f"Table '{table}' truncated.")
            except Exception as e:
                print(f"Failed to truncate table '{table}': {e}")

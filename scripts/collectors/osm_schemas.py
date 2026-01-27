"""Pandera schemas for validating OpenStreetMap API responses.

This module provides Pandera DataFrameSchema validators for OSM trail data
collected via osmnx. Unlike the NPS API which returns JSON (validated with
Pydantic), OSM data comes as GeoDataFrames and requires tabular validation.

Two schemas are provided:
1. OSMRawTrailsSchema - validates data immediately after OSM query
2. OSMProcessedTrailsSchema - validates data before saving to file/database
"""

import os
import sys

import pandera.pandas as pa
from pandera.pandas import Check, Column, DataFrameSchema
from shapely.geometry import LineString, MultiLineString
from shapely.geometry.base import BaseGeometry

# Load config to get validation thresholds
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
from config.settings import config


def is_valid_geometry(series) -> bool:
    """Check if all geometries in series are valid using Shapely.

    Args:
        series: Pandas/GeoPandas series containing geometry objects

    Returns:
        bool: True if all geometries are valid, False otherwise
    """
    try:
        return series.apply(
            lambda geom: geom is not None
            and isinstance(geom, BaseGeometry)
            and geom.is_valid
        ).all()
    except:
        return False


def is_linestring_type(series) -> bool:
    """Check if all geometries in series are LineString or MultiLineString.

    Args:
        series: Pandas/GeoPandas series containing geometry objects

    Returns:
        bool: True if all geometries are LineString or MultiLineString
    """
    try:
        return series.apply(
            lambda geom: geom is not None
            and isinstance(geom, (LineString, MultiLineString))
        ).all()
    except:
        return False


def is_positive_integer(series) -> bool:
    """Check if all values in series are positive integers.

    Args:
        series: Pandas series to check

    Returns:
        bool: True if all values are positive integers
    """
    try:
        return (series > 0).all()
    except (ValueError, TypeError):
        return False


# Schema for raw OSM data immediately after query
OSMRawTrailsSchema = DataFrameSchema(
    columns={
        "osm_id": Column(
            pa.Int64,
            checks=[
                Check(
                    is_positive_integer,
                    error="osm_id must be a positive integer",
                )
            ],
            nullable=False,
            description="OpenStreetMap feature ID",
        ),
        "highway": Column(
            pa.String,
            checks=[
                Check.isin(
                    ["path", "footway", "track", "steps", "cycleway"],
                    error="highway must be a valid OSM trail type",
                )
            ],
            nullable=False,
            description="OSM highway tag indicating trail type",
        ),
        "name": Column(
            pa.String,
            nullable=False,  # We filter for named trails only
            checks=[
                Check(
                    lambda s: s.str.strip().str.len() > 0,
                    error="Trail name cannot be empty or whitespace",
                )
            ],
            description="Trail name from OSM",
        ),
        "geometry": Column(
            checks=[
                Check(
                    is_valid_geometry,
                    error="Geometry must be a valid Shapely geometry",
                ),
                Check(
                    is_linestring_type,
                    error="Geometry must be LineString or MultiLineString",
                ),
            ],
            nullable=False,
            description="Trail geometry (LineString or MultiLineString)",
        ),
    },
    strict=False,  # Allow additional columns from OSM (we'll filter them later)
    coerce=True,  # Coerce types where possible
    description="Schema for raw OSM trail data immediately after API query",
)


# Schema for processed OSM data before saving
OSMProcessedTrailsSchema = DataFrameSchema(
    columns={
        "osm_id": Column(
            pa.Int64,
            checks=[
                Check(
                    is_positive_integer,
                    error="osm_id must be a positive integer",
                )
            ],
            nullable=False,
            description="OpenStreetMap feature ID (may be modified for clipped segments)",
        ),
        "park_code": Column(
            pa.String,
            checks=[
                Check(
                    lambda s: s.str.len() == 4,
                    error="park_code must be exactly 4 characters",
                ),
                Check(
                    lambda s: s.str.islower(),
                    error="park_code must be lowercase (NPS standard format)",
                ),
            ],
            nullable=False,
            description="NPS park code (4 lowercase characters, e.g. 'zion', 'acad')",
        ),
        "highway": Column(
            pa.String,
            checks=[
                Check.isin(
                    ["path", "footway", "track", "steps", "cycleway"],
                    error="highway must be a valid OSM trail type",
                )
            ],
            nullable=False,
            description="OSM highway tag indicating trail type",
        ),
        "name": Column(
            pa.String,
            nullable=False,
            checks=[
                Check(
                    lambda s: s.str.strip().str.len() > 0,
                    error="Trail name cannot be empty or whitespace",
                )
            ],
            description="Trail name from OSM",
        ),
        "source": Column(
            pa.String,
            nullable=True,  # Source can be None
            description="Data source attribution from OSM (optional)",
        ),
        "length_miles": Column(
            pa.Float64,
            checks=[
                Check.greater_than_or_equal_to(
                    config.OSM_MIN_TRAIL_LENGTH_MILES,
                    error=f"Trail length must be >= {config.OSM_MIN_TRAIL_LENGTH_MILES} miles",
                ),
                Check.less_than_or_equal_to(
                    config.OSM_MAX_TRAIL_LENGTH_MILES,
                    error=f"Trail length must be <= {config.OSM_MAX_TRAIL_LENGTH_MILES} miles",
                ),
            ],
            nullable=False,
            description="Trail length in miles (calculated using projected CRS)",
        ),
        "geometry_type": Column(
            pa.String,
            checks=[
                Check.isin(
                    ["LineString", "MultiLineString"],
                    error="geometry_type must be LineString or MultiLineString",
                )
            ],
            nullable=False,
            description="Type of geometry (LineString or MultiLineString)",
        ),
        "geometry": Column(
            checks=[
                Check(
                    is_valid_geometry,
                    error="Geometry must be a valid Shapely geometry",
                ),
                Check(
                    is_linestring_type,
                    error="Geometry must be LineString or MultiLineString",
                ),
            ],
            nullable=False,
            description="Trail geometry (LineString or MultiLineString)",
        ),
    },
    strict=True,  # Enforce exact columns for processed data
    coerce=True,  # Coerce types where possible
    description="Schema for processed OSM trail data before saving to file/database",
)

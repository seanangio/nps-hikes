"""Validation schemas for TNM (The National Map) hiking trail data.

This module provides two types of validation schemas:
1. Pydantic schemas - Validate GeoJSON API responses from TNM REST API
2. Pandera schemas - Validate processed GeoDataFrame data before saving

The dual validation approach catches:
- Structural issues in API responses (Pydantic)
- Data quality issues after processing (Pandera)
"""

from __future__ import annotations

import os
import sys
from typing import Any, Literal

import pandas as pd
import pandera.pandas as pa
from pandera.pandas import Check, Column, DataFrameSchema
from pydantic import BaseModel, ConfigDict, Field, field_validator
from shapely.geometry import LineString, MultiLineString
from shapely.geometry.base import BaseGeometry

# Load config to get validation thresholds
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
from config.settings import config

# =============================================================================
# PYDANTIC SCHEMAS - For validating TNM API GeoJSON responses
# =============================================================================


class TNMGeometry(BaseModel):
    """Validates GeoJSON geometry structure from TNM API.

    The TNM API returns GeoJSON geometries. This schema validates the basic
    structure before conversion to a GeoDataFrame. Detailed geometry validation
    happens later with Pandera.
    """

    type: str = Field(..., description="GeoJSON geometry type")
    coordinates: list = Field(..., description="Coordinate array")

    @field_validator("type")
    @classmethod
    def validate_geometry_type(cls, v: str) -> str:
        """Ensure geometry type is a valid GeoJSON type.

        Args:
            v: The geometry type string

        Returns:
            The validated geometry type

        Raises:
            ValueError: If geometry type is not a valid GeoJSON type
        """
        valid_types = {
            "Point",
            "LineString",
            "MultiLineString",
            "Polygon",
            "MultiPolygon",
        }
        if v not in valid_types:
            raise ValueError(
                f"Invalid geometry type '{v}'. Must be one of: {valid_types}"
            )
        return v


class TNMFeatureProperties(BaseModel):
    """Validates properties from TNM trail feature.

    Only validates the permanent identifier which is required for primary key.
    All other fields are optional since the TNM API may not return all fields
    for every feature.
    """

    permanentidentifier: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Globally unique identifier from TNM API",
    )

    # All other fields are optional - TNM API may not return them
    name: str | None = Field(default=None, description="Trail name")
    lengthmiles: float | None = Field(default=None, description="Trail length in miles")

    # Allow extra fields from API that we haven't explicitly defined
    model_config = ConfigDict(extra="allow")


class TNMFeature(BaseModel):
    """Validates a single GeoJSON Feature from TNM API.

    A Feature contains a geometry and properties object following the
    GeoJSON specification.
    """

    type: Literal["Feature"] = Field(..., description="Must be 'Feature'")
    geometry: TNMGeometry = Field(..., description="The geometry object")
    properties: TNMFeatureProperties = Field(..., description="Feature properties")


class TNMFeatureCollection(BaseModel):
    """Validates TNM API GeoJSON FeatureCollection response.

    The TNM API returns a FeatureCollection containing an array of Features.
    This is the top-level response structure.
    """

    type: Literal["FeatureCollection"] = Field(
        ..., description="Must be 'FeatureCollection'"
    )
    features: list[TNMFeature] = Field(..., description="Array of trail features")


# =============================================================================
# PANDERA SCHEMAS - For validating processed GeoDataFrame data
# =============================================================================


def is_valid_geometry(series: pd.Series[Any]) -> bool:
    """Check if all geometries in series are valid using Shapely.

    Args:
        series: Pandas/GeoPandas series containing geometry objects

    Returns:
        bool: True if all geometries are valid, False otherwise
    """
    try:
        return bool(
            series.apply(
                lambda geom: (
                    geom is not None
                    and isinstance(geom, BaseGeometry)
                    and geom.is_valid
                )
            ).all()
        )
    except Exception:
        return False


def is_linestring_type(series: pd.Series[Any]) -> bool:
    """Check if all geometries in series are LineString or MultiLineString.

    Args:
        series: Pandas/GeoPandas series containing geometry objects

    Returns:
        bool: True if all geometries are LineString or MultiLineString
    """
    try:
        return bool(
            series.apply(
                lambda geom: (
                    geom is not None and isinstance(geom, (LineString, MultiLineString))
                )
            ).all()
        )
    except Exception:
        return False


# Define the processed trails schema with required and optional columns
TNMProcessedTrailsSchema = DataFrameSchema(
    columns={
        # =====================================================================
        # REQUIRED COLUMNS - Must exist and pass validation
        # =====================================================================
        "permanent_identifier": Column(
            pa.String,
            checks=[
                Check(
                    lambda s: s.str.len() > 0,
                    error="permanent_identifier cannot be empty",
                ),
                Check(
                    lambda s: s.str.len() <= 100,
                    error="permanent_identifier max 100 chars",
                ),
            ],
            nullable=False,
            description="Globally unique identifier from TNM API (primary key)",
        ),
        "park_code": Column(
            pa.String,
            checks=[
                Check(lambda s: s.str.len() == 4, error="park_code must be 4 chars"),
                Check(lambda s: s.str.islower(), error="park_code must be lowercase"),
            ],
            nullable=False,
            description="NPS park code (4 lowercase characters)",
        ),
        "length_miles": Column(
            pa.Float,
            checks=[
                Check.greater_than_or_equal_to(
                    config.TNM_MIN_TRAIL_LENGTH_MI,
                    error=f"length_miles must be >= {config.TNM_MIN_TRAIL_LENGTH_MI}",
                ),
                Check.less_than(1000, error="length_miles must be < 1000"),
            ],
            nullable=False,
            description="Trail length in miles",
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
            description="Type of geometry",
        ),
        "geometry": Column(
            checks=[
                Check(is_valid_geometry, error="Geometry must be valid"),
                Check(
                    is_linestring_type,
                    error="Geometry must be LineString or MultiLineString",
                ),
            ],
            nullable=False,
            description="Trail geometry (LineString or MultiLineString)",
        ),
        "collected_at": Column(
            pa.String,  # Will be timestamp string in ISO format
            nullable=False,
            description="Timestamp when data was collected",
        ),
        # =====================================================================
        # OPTIONAL STRING COLUMNS - Validate max length if present
        # =====================================================================
        "name": Column(
            pa.String,
            checks=[Check(lambda s: s.str.len() <= 500, error="name max 500 chars")],
            nullable=True,
            required=False,
            description="Trail name",
        ),
        "name_alternate": Column(
            pa.String,
            checks=[
                Check(
                    lambda s: s.str.len() <= 500, error="name_alternate max 500 chars"
                )
            ],
            nullable=True,
            required=False,
            description="Alternate trail name",
        ),
        "trail_number": Column(
            pa.String,
            checks=[
                Check(lambda s: s.str.len() <= 50, error="trail_number max 50 chars")
            ],
            nullable=True,
            required=False,
            description="Trail number",
        ),
        "trail_number_alternate": Column(
            pa.String,
            checks=[
                Check(
                    lambda s: s.str.len() <= 50,
                    error="trail_number_alternate max 50 chars",
                )
            ],
            nullable=True,
            required=False,
            description="Alternate trail number",
        ),
        "source_feature_id": Column(
            pa.String,
            checks=[
                Check(
                    lambda s: s.str.len() <= 100,
                    error="source_feature_id max 100 chars",
                )
            ],
            nullable=True,
            required=False,
            description="Source feature identifier",
        ),
        "source_dataset_id": Column(
            pa.String,
            checks=[
                Check(
                    lambda s: s.str.len() <= 100,
                    error="source_dataset_id max 100 chars",
                )
            ],
            nullable=True,
            required=False,
            description="Source dataset identifier",
        ),
        "source_originator": Column(
            pa.String,
            checks=[
                Check(
                    lambda s: s.str.len() <= 100,
                    error="source_originator max 100 chars",
                )
            ],
            nullable=True,
            required=False,
            description="Source originator",
        ),
        "trail_type": Column(
            pa.String,
            checks=[
                Check(lambda s: s.str.len() <= 100, error="trail_type max 100 chars")
            ],
            nullable=True,
            required=False,
            description="Type of trail (e.g., Terra Trail)",
        ),
        "primary_trail_maintainer": Column(
            pa.String,
            checks=[
                Check(
                    lambda s: s.str.len() <= 100,
                    error="primary_trail_maintainer max 100 chars",
                )
            ],
            nullable=True,
            required=False,
            description="Organization responsible for trail maintenance",
        ),
        "national_trail_designation": Column(
            pa.String,
            checks=[
                Check(
                    lambda s: s.str.len() <= 500,
                    error="national_trail_designation max 500 chars",
                )
            ],
            nullable=True,
            required=False,
            description="National trail designation",
        ),
        "source_data_description": Column(
            pa.String,
            checks=[
                Check(
                    lambda s: s.str.len() <= 500,
                    error="source_data_description max 500 chars",
                )
            ],
            nullable=True,
            required=False,
            description="Description of source data",
        ),
        "global_id": Column(
            pa.String,
            checks=[
                Check(lambda s: s.str.len() <= 100, error="global_id max 100 chars")
            ],
            nullable=True,
            required=False,
            description="Global identifier",
        ),
        # =====================================================================
        # OPTIONAL BOOLEAN COLUMNS - Must be Y, N, or None
        # =====================================================================
        "hiker_pedestrian": Column(
            pa.String,
            checks=[
                Check.isin(["Y", "N"], error="hiker_pedestrian must be Y, N, or None")
            ],
            nullable=True,
            required=False,
            description="Allows hiking/pedestrian use (Y/N)",
        ),
        "bicycle": Column(
            pa.String,
            checks=[Check.isin(["Y", "N"], error="bicycle must be Y, N, or None")],
            nullable=True,
            required=False,
            description="Allows bicycle use (Y/N)",
        ),
        "pack_saddle": Column(
            pa.String,
            checks=[Check.isin(["Y", "N"], error="pack_saddle must be Y, N, or None")],
            nullable=True,
            required=False,
            description="Allows pack/saddle use (Y/N)",
        ),
        "atv": Column(
            pa.String,
            checks=[Check.isin(["Y", "N"], error="atv must be Y, N, or None")],
            nullable=True,
            required=False,
            description="Allows ATV use (Y/N)",
        ),
        "motorcycle": Column(
            pa.String,
            checks=[Check.isin(["Y", "N"], error="motorcycle must be Y, N, or None")],
            nullable=True,
            required=False,
            description="Allows motorcycle use (Y/N)",
        ),
        "ohv_over_50_inches": Column(
            pa.String,
            checks=[
                Check.isin(["Y", "N"], error="ohv_over_50_inches must be Y, N, or None")
            ],
            nullable=True,
            required=False,
            description="Allows OHV over 50 inches (Y/N)",
        ),
        "snowshoe": Column(
            pa.String,
            checks=[Check.isin(["Y", "N"], error="snowshoe must be Y, N, or None")],
            nullable=True,
            required=False,
            description="Allows snowshoe use (Y/N)",
        ),
        "cross_country_ski": Column(
            pa.String,
            checks=[
                Check.isin(["Y", "N"], error="cross_country_ski must be Y, N, or None")
            ],
            nullable=True,
            required=False,
            description="Allows cross-country ski use (Y/N)",
        ),
        "dogsled": Column(
            pa.String,
            checks=[Check.isin(["Y", "N"], error="dogsled must be Y, N, or None")],
            nullable=True,
            required=False,
            description="Allows dogsled use (Y/N)",
        ),
        "snowmobile": Column(
            pa.String,
            checks=[Check.isin(["Y", "N"], error="snowmobile must be Y, N, or None")],
            nullable=True,
            required=False,
            description="Allows snowmobile use (Y/N)",
        ),
        "non_motorized_watercraft": Column(
            pa.String,
            checks=[
                Check.isin(
                    ["Y", "N"], error="non_motorized_watercraft must be Y, N, or None"
                )
            ],
            nullable=True,
            required=False,
            description="Allows non-motorized watercraft (Y/N)",
        ),
        "motorized_watercraft": Column(
            pa.String,
            checks=[
                Check.isin(
                    ["Y", "N"], error="motorized_watercraft must be Y, N, or None"
                )
            ],
            nullable=True,
            required=False,
            description="Allows motorized watercraft (Y/N)",
        ),
        # =====================================================================
        # OPTIONAL NUMERIC COLUMNS
        # =====================================================================
        "object_id": Column(
            pa.Int,
            nullable=True,
            required=False,
            description="Object ID from TNM",
        ),
        "load_date": Column(
            pa.Int,
            nullable=True,
            required=False,
            description="Load date (BIGINT timestamp)",
        ),
        "network_length": Column(
            pa.Float,
            nullable=True,
            required=False,
            description="Network length",
        ),
        "shape_length": Column(
            pa.Float,
            nullable=True,
            required=False,
            description="Shape length in original CRS",
        ),
    },
    strict=False,  # Allow extra columns that might come from API
    coerce=True,  # Coerce types where possible
    description="Schema for processed TNM trail data before saving to file/database",
)

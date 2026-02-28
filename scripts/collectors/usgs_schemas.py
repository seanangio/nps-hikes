"""Pydantic schemas for validating USGS Elevation API responses.

This module provides Pydantic validators for USGS Elevation Point Query Service
(EPQS) API responses and elevation profile data. Unlike TNM which uses both
Pydantic and Pandera, USGS validation uses Pydantic only since we're working
with JSON responses and storing data as JSON (not tabular data).

Three validation stages:
1. USGSElevationResponse - Validates raw API response from USGS EPQS
2. USGSElevationPoint - Validates individual elevation points
3. USGSTrailElevationProfile - Validates complete profile before database storage
"""

from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator


class USGSElevationResponse(BaseModel):
    """Validates USGS Elevation Point Query Service (EPQS) API response.

    The USGS EPQS API returns a simple JSON structure with an elevation value.
    Example response: {"value": 123.45}

    Special cases:
    - value = -1000000: Indicates "no data available" for this location
    - value = None: API returned null (treated as no data)
    """

    value: float | int | None = Field(
        ..., description="Elevation in meters, or None if no data"
    )

    @field_validator("value")
    @classmethod
    def validate_elevation_value(cls, v: float | int | None) -> float | None:
        """Validate elevation value is within reasonable range or None.

        Args:
            v: The elevation value from API

        Returns:
            The validated elevation value or None

        Raises:
            ValueError: If elevation is outside reasonable range
        """
        # None is acceptable (no data)
        if v is None:
            return None

        # -1000000 is USGS sentinel value for "no data available"
        if v == -1000000:
            return None

        # Reasonable elevation range for Earth's land surface
        # Dead Sea: -430m, Mount Everest: 8849m, adding buffer
        if not (-500 <= v <= 9000):
            raise ValueError(
                f"Elevation {v}m outside valid range [-500, 9000]. "
                "This may indicate an API error or invalid location."
            )

        return float(v)


class USGSElevationPoint(BaseModel):
    """Validates individual elevation point in a trail profile.

    Each point represents a sampled location along a trail's geometry with
    its distance from the start and elevation.
    """

    point_index: int = Field(..., ge=0, description="Point index in the profile")
    distance_m: float = Field(
        ..., ge=0, description="Distance from trail start (meters)"
    )
    latitude: float = Field(..., description="Point latitude (WGS84)")
    longitude: float = Field(..., description="Point longitude (WGS84)")
    elevation_m: float = Field(..., description="Elevation at this point (meters)")

    @field_validator("latitude")
    @classmethod
    def validate_latitude(cls, v: float) -> float:
        """Validate latitude is within valid range [-90, 90].

        Args:
            v: The latitude value

        Returns:
            The validated latitude

        Raises:
            ValueError: If latitude is outside valid range
        """
        if not (-90 <= v <= 90):
            raise ValueError(f"Latitude {v} outside valid range [-90, 90]")
        return v

    @field_validator("longitude")
    @classmethod
    def validate_longitude(cls, v: float) -> float:
        """Validate longitude is within valid range [-180, 180].

        Args:
            v: The longitude value

        Returns:
            The validated longitude

        Raises:
            ValueError: If longitude is outside valid range [-180, 180]
        """
        if not (-180 <= v <= 180):
            raise ValueError(f"Longitude {v} outside valid range [-180, 180]")
        return v

    @field_validator("elevation_m")
    @classmethod
    def validate_elevation(cls, v: float) -> float:
        """Validate elevation is within reasonable range.

        Args:
            v: The elevation value in meters

        Returns:
            The validated elevation

        Raises:
            ValueError: If elevation is outside reasonable range
        """
        if not (-500 <= v <= 9000):
            raise ValueError(
                f"Elevation {v}m outside valid range [-500, 9000]. "
                "This may indicate an API error."
            )
        return v


class USGSTrailElevationProfile(BaseModel):
    """Validates complete elevation profile before database storage.

    An elevation profile contains all sampled points along a trail, along with
    metadata about the trail and collection status.
    """

    gmaps_location_id: int | str = Field(
        ..., description="Google Maps location ID (integer or string)"
    )

    @field_validator("gmaps_location_id")
    @classmethod
    def validate_gmaps_location_id(cls, v: int | str) -> int | str:
        """Validate gmaps_location_id is not empty if string.

        Args:
            v: The gmaps_location_id (int or str)

        Returns:
            The validated gmaps_location_id

        Raises:
            ValueError: If string is empty
        """
        if isinstance(v, str) and len(v) == 0:
            raise ValueError("gmaps_location_id cannot be empty string")
        if isinstance(v, int) and v <= 0:
            raise ValueError("gmaps_location_id must be positive if integer")
        return v

    trail_name: str = Field(..., min_length=1, description="Trail name")
    park_code: str = Field(
        ..., min_length=4, max_length=4, description="NPS park code (4 characters)"
    )
    source: str = Field(
        ..., min_length=1, description="Trail data source (e.g., 'osm', 'tnm')"
    )
    elevation_points: list[USGSElevationPoint] = Field(
        ..., description="List of elevation points along the trail"
    )
    collection_status: Literal["COMPLETE", "PARTIAL", "FAILED"] = Field(
        ..., description="Status of elevation data collection"
    )
    failed_points_count: int = Field(
        ..., ge=0, description="Number of points that failed to collect"
    )
    total_points_count: int = Field(
        ..., ge=1, description="Total number of points attempted"
    )

    @field_validator("park_code")
    @classmethod
    def validate_park_code(cls, v: str) -> str:
        """Validate park code is lowercase (NPS standard format).

        Args:
            v: The park code

        Returns:
            The validated park code

        Raises:
            ValueError: If park code is not lowercase
        """
        if not v.islower():
            raise ValueError(f"Park code '{v}' must be lowercase (NPS standard format)")
        return v

    @model_validator(mode="after")
    def validate_point_counts(self) -> Self:
        """Validate that failed_points_count doesn't exceed total_points_count.

        Also validates that collection_status is consistent with point counts
        and elevation_points list length.

        Returns:
            self: The validated model instance

        Raises:
            ValueError: If point counts are inconsistent
        """
        # Failed points can't exceed total points
        if self.failed_points_count > self.total_points_count:
            raise ValueError(
                f"failed_points_count ({self.failed_points_count}) cannot exceed "
                f"total_points_count ({self.total_points_count})"
            )

        # Number of successful points should match elevation_points list length
        expected_successful = self.total_points_count - self.failed_points_count
        actual_successful = len(self.elevation_points)

        if actual_successful != expected_successful:
            raise ValueError(
                f"Elevation points list length ({actual_successful}) doesn't match "
                f"expected successful points ({expected_successful} = "
                f"{self.total_points_count} total - {self.failed_points_count} failed)"
            )

        # Validate status is consistent with success rate
        failure_rate = (
            self.failed_points_count / self.total_points_count
            if self.total_points_count > 0
            else 0
        )

        if self.collection_status == "COMPLETE" and self.failed_points_count > 0:
            raise ValueError(
                f"collection_status is 'COMPLETE' but {self.failed_points_count} "
                "points failed. Should be 'PARTIAL' or 'FAILED'."
            )

        if self.collection_status == "FAILED" and failure_rate < 0.5:
            raise ValueError(
                f"collection_status is 'FAILED' but failure rate is only "
                f"{failure_rate:.1%}. Should be 'COMPLETE' or 'PARTIAL'."
            )

        return self

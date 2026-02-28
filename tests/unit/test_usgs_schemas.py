"""Unit tests for USGS elevation data validation schemas.

Tests the Pydantic validation schemas used for validating USGS Elevation
Point Query Service (EPQS) API responses and elevation profile data.
"""

import pytest
from pydantic import ValidationError

from scripts.collectors.usgs_schemas import (
    USGSElevationPoint,
    USGSElevationResponse,
    USGSTrailElevationProfile,
)


class TestUSGSElevationResponse:
    """Test USGS EPQS API response validation."""

    def test_valid_response_with_elevation(self):
        """Test that valid API response with elevation passes validation."""
        response = {"value": 123.45}
        validated = USGSElevationResponse(**response)
        assert validated.value == 123.45

    def test_valid_response_with_integer_elevation(self):
        """Test that integer elevation values are accepted."""
        response = {"value": 500}
        validated = USGSElevationResponse(**response)
        assert validated.value == 500.0

    def test_valid_response_with_null_value(self):
        """Test that null/None values are accepted (no data available)."""
        response = {"value": None}
        validated = USGSElevationResponse(**response)
        assert validated.value is None

    def test_no_data_sentinel_value_returns_none(self):
        """Test that USGS sentinel value -1000000 is converted to None."""
        response = {"value": -1000000}
        validated = USGSElevationResponse(**response)
        assert validated.value is None

    def test_negative_elevation_within_range(self):
        """Test that valid negative elevations (e.g., Dead Sea) are accepted."""
        response = {"value": -430}  # Dead Sea level
        validated = USGSElevationResponse(**response)
        assert validated.value == -430

    def test_high_elevation_within_range(self):
        """Test that high elevations (e.g., mountains) are accepted."""
        response = {"value": 8849}  # Mount Everest
        validated = USGSElevationResponse(**response)
        assert validated.value == 8849

    def test_elevation_below_minimum_fails(self):
        """Test that elevation below -500m fails validation."""
        response = {"value": -600}
        with pytest.raises(ValidationError, match="outside valid range"):
            USGSElevationResponse(**response)

    def test_elevation_above_maximum_fails(self):
        """Test that elevation above 9000m fails validation."""
        response = {"value": 10000}
        with pytest.raises(ValidationError, match="outside valid range"):
            USGSElevationResponse(**response)

    def test_missing_value_field_fails(self):
        """Test that response without 'value' field fails validation."""
        response = {}
        with pytest.raises(ValidationError):
            USGSElevationResponse(**response)

    def test_invalid_value_type_fails(self):
        """Test that non-numeric value fails validation."""
        response = {"value": "not_a_number"}
        with pytest.raises(ValidationError):
            USGSElevationResponse(**response)


class TestUSGSElevationPoint:
    """Test individual elevation point validation."""

    def test_valid_elevation_point(self):
        """Test that valid elevation point passes validation."""
        point = {
            "point_index": 0,
            "distance_m": 0.0,
            "latitude": 44.3386,
            "longitude": -68.2733,
            "elevation_m": 470.5,
        }
        validated = USGSElevationPoint(**point)
        assert validated.point_index == 0
        assert validated.latitude == 44.3386
        assert validated.elevation_m == 470.5

    def test_negative_point_index_fails(self):
        """Test that negative point index fails validation."""
        point = {
            "point_index": -1,
            "distance_m": 0.0,
            "latitude": 44.3386,
            "longitude": -68.2733,
            "elevation_m": 470.5,
        }
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            USGSElevationPoint(**point)

    def test_negative_distance_fails(self):
        """Test that negative distance fails validation."""
        point = {
            "point_index": 0,
            "distance_m": -10.0,
            "latitude": 44.3386,
            "longitude": -68.2733,
            "elevation_m": 470.5,
        }
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            USGSElevationPoint(**point)

    def test_latitude_below_minimum_fails(self):
        """Test that latitude below -90 fails validation."""
        point = {
            "point_index": 0,
            "distance_m": 0.0,
            "latitude": -91.0,
            "longitude": -68.2733,
            "elevation_m": 470.5,
        }
        with pytest.raises(ValidationError, match=r"Latitude .* outside valid range"):
            USGSElevationPoint(**point)

    def test_latitude_above_maximum_fails(self):
        """Test that latitude above 90 fails validation."""
        point = {
            "point_index": 0,
            "distance_m": 0.0,
            "latitude": 91.0,
            "longitude": -68.2733,
            "elevation_m": 470.5,
        }
        with pytest.raises(ValidationError, match=r"Latitude .* outside valid range"):
            USGSElevationPoint(**point)

    def test_longitude_below_minimum_fails(self):
        """Test that longitude below -180 fails validation."""
        point = {
            "point_index": 0,
            "distance_m": 0.0,
            "latitude": 44.3386,
            "longitude": -181.0,
            "elevation_m": 470.5,
        }
        with pytest.raises(ValidationError, match=r"Longitude .* outside valid range"):
            USGSElevationPoint(**point)

    def test_longitude_above_maximum_fails(self):
        """Test that longitude above 180 fails validation."""
        point = {
            "point_index": 0,
            "distance_m": 0.0,
            "latitude": 44.3386,
            "longitude": 181.0,
            "elevation_m": 470.5,
        }
        with pytest.raises(ValidationError, match=r"Longitude .* outside valid range"):
            USGSElevationPoint(**point)

    def test_elevation_below_minimum_fails(self):
        """Test that elevation below -500m fails validation."""
        point = {
            "point_index": 0,
            "distance_m": 0.0,
            "latitude": 44.3386,
            "longitude": -68.2733,
            "elevation_m": -600.0,
        }
        with pytest.raises(ValidationError, match=r"Elevation .* outside valid range"):
            USGSElevationPoint(**point)

    def test_elevation_above_maximum_fails(self):
        """Test that elevation above 9000m fails validation."""
        point = {
            "point_index": 0,
            "distance_m": 0.0,
            "latitude": 44.3386,
            "longitude": -68.2733,
            "elevation_m": 10000.0,
        }
        with pytest.raises(ValidationError, match=r"Elevation .* outside valid range"):
            USGSElevationPoint(**point)

    def test_missing_required_field_fails(self):
        """Test that missing required fields fail validation."""
        point = {
            "point_index": 0,
            "distance_m": 0.0,
            # Missing latitude, longitude, elevation_m
        }
        with pytest.raises(ValidationError):
            USGSElevationPoint(**point)


class TestUSGSTrailElevationProfile:
    """Test complete elevation profile validation."""

    @pytest.fixture
    def valid_elevation_points(self):
        """Fixture providing valid elevation points."""
        return [
            {
                "point_index": 0,
                "distance_m": 0.0,
                "latitude": 44.3386,
                "longitude": -68.2733,
                "elevation_m": 470.5,
            },
            {
                "point_index": 1,
                "distance_m": 100.0,
                "latitude": 44.3390,
                "longitude": -68.2740,
                "elevation_m": 480.2,
            },
            {
                "point_index": 2,
                "distance_m": 200.0,
                "latitude": 44.3394,
                "longitude": -68.2747,
                "elevation_m": 490.8,
            },
        ]

    def test_valid_complete_profile(self, valid_elevation_points):
        """Test that valid complete profile passes validation."""
        profile = {
            "gmaps_location_id": "ChIJtest123",
            "trail_name": "Precipice Trail",
            "park_code": "acad",
            "source": "osm",
            "elevation_points": valid_elevation_points,
            "collection_status": "COMPLETE",
            "failed_points_count": 0,
            "total_points_count": 3,
        }
        validated = USGSTrailElevationProfile(**profile)
        assert validated.trail_name == "Precipice Trail"
        assert validated.park_code == "acad"
        assert len(validated.elevation_points) == 3

    def test_valid_profile_with_integer_location_id(self, valid_elevation_points):
        """Test that profile with integer gmaps_location_id passes validation."""
        profile = {
            "gmaps_location_id": 48,
            "trail_name": "Precipice Trail",
            "park_code": "acad",
            "source": "osm",
            "elevation_points": valid_elevation_points,
            "collection_status": "COMPLETE",
            "failed_points_count": 0,
            "total_points_count": 3,
        }
        validated = USGSTrailElevationProfile(**profile)
        assert validated.gmaps_location_id == 48
        assert isinstance(validated.gmaps_location_id, int)

    def test_valid_partial_profile(self, valid_elevation_points):
        """Test that partial profile with some failures passes validation."""
        profile = {
            "gmaps_location_id": "ChIJtest123",
            "trail_name": "Precipice Trail",
            "park_code": "acad",
            "source": "tnm",
            "elevation_points": valid_elevation_points,
            "collection_status": "PARTIAL",
            "failed_points_count": 1,
            "total_points_count": 4,  # 3 successful + 1 failed
        }
        validated = USGSTrailElevationProfile(**profile)
        assert validated.collection_status == "PARTIAL"
        assert validated.failed_points_count == 1

    def test_empty_gmaps_location_id_fails(self, valid_elevation_points):
        """Test that empty gmaps_location_id fails validation."""
        profile = {
            "gmaps_location_id": "",
            "trail_name": "Precipice Trail",
            "park_code": "acad",
            "source": "osm",
            "elevation_points": valid_elevation_points,
            "collection_status": "COMPLETE",
            "failed_points_count": 0,
            "total_points_count": 3,
        }
        with pytest.raises(ValidationError, match="cannot be empty"):
            USGSTrailElevationProfile(**profile)

    def test_negative_gmaps_location_id_fails(self, valid_elevation_points):
        """Test that negative integer gmaps_location_id fails validation."""
        profile = {
            "gmaps_location_id": -1,
            "trail_name": "Precipice Trail",
            "park_code": "acad",
            "source": "osm",
            "elevation_points": valid_elevation_points,
            "collection_status": "COMPLETE",
            "failed_points_count": 0,
            "total_points_count": 3,
        }
        with pytest.raises(ValidationError, match="must be positive"):
            USGSTrailElevationProfile(**profile)

    def test_zero_gmaps_location_id_fails(self, valid_elevation_points):
        """Test that zero gmaps_location_id fails validation."""
        profile = {
            "gmaps_location_id": 0,
            "trail_name": "Precipice Trail",
            "park_code": "acad",
            "source": "osm",
            "elevation_points": valid_elevation_points,
            "collection_status": "COMPLETE",
            "failed_points_count": 0,
            "total_points_count": 3,
        }
        with pytest.raises(ValidationError, match="must be positive"):
            USGSTrailElevationProfile(**profile)

    def test_empty_trail_name_fails(self, valid_elevation_points):
        """Test that empty trail name fails validation."""
        profile = {
            "gmaps_location_id": "ChIJtest123",
            "trail_name": "",
            "park_code": "acad",
            "source": "osm",
            "elevation_points": valid_elevation_points,
            "collection_status": "COMPLETE",
            "failed_points_count": 0,
            "total_points_count": 3,
        }
        with pytest.raises(ValidationError, match="at least 1 character"):
            USGSTrailElevationProfile(**profile)

    def test_invalid_park_code_length_fails(self, valid_elevation_points):
        """Test that park code not exactly 4 characters fails validation."""
        profile = {
            "gmaps_location_id": "ChIJtest123",
            "trail_name": "Precipice Trail",
            "park_code": "acadnp",  # Too long
            "source": "osm",
            "elevation_points": valid_elevation_points,
            "collection_status": "COMPLETE",
            "failed_points_count": 0,
            "total_points_count": 3,
        }
        with pytest.raises(ValidationError):
            USGSTrailElevationProfile(**profile)

    def test_uppercase_park_code_fails(self, valid_elevation_points):
        """Test that uppercase park code fails validation."""
        profile = {
            "gmaps_location_id": "ChIJtest123",
            "trail_name": "Precipice Trail",
            "park_code": "ACAD",  # Uppercase
            "source": "osm",
            "elevation_points": valid_elevation_points,
            "collection_status": "COMPLETE",
            "failed_points_count": 0,
            "total_points_count": 3,
        }
        with pytest.raises(ValidationError, match="must be lowercase"):
            USGSTrailElevationProfile(**profile)

    def test_invalid_collection_status_fails(self, valid_elevation_points):
        """Test that invalid collection status fails validation."""
        profile = {
            "gmaps_location_id": "ChIJtest123",
            "trail_name": "Precipice Trail",
            "park_code": "acad",
            "source": "osm",
            "elevation_points": valid_elevation_points,
            "collection_status": "INVALID",
            "failed_points_count": 0,
            "total_points_count": 3,
        }
        with pytest.raises(ValidationError):
            USGSTrailElevationProfile(**profile)

    def test_negative_failed_points_count_fails(self, valid_elevation_points):
        """Test that negative failed_points_count fails validation."""
        profile = {
            "gmaps_location_id": "ChIJtest123",
            "trail_name": "Precipice Trail",
            "park_code": "acad",
            "source": "osm",
            "elevation_points": valid_elevation_points,
            "collection_status": "COMPLETE",
            "failed_points_count": -1,
            "total_points_count": 3,
        }
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            USGSTrailElevationProfile(**profile)

    def test_zero_total_points_count_fails(self, valid_elevation_points):
        """Test that zero total_points_count fails validation."""
        profile = {
            "gmaps_location_id": "ChIJtest123",
            "trail_name": "Precipice Trail",
            "park_code": "acad",
            "source": "osm",
            "elevation_points": [],
            "collection_status": "FAILED",
            "failed_points_count": 0,
            "total_points_count": 0,
        }
        with pytest.raises(ValidationError, match="greater than or equal to 1"):
            USGSTrailElevationProfile(**profile)

    def test_failed_count_exceeds_total_fails(self, valid_elevation_points):
        """Test that failed_points_count > total_points_count fails validation."""
        profile = {
            "gmaps_location_id": "ChIJtest123",
            "trail_name": "Precipice Trail",
            "park_code": "acad",
            "source": "osm",
            "elevation_points": valid_elevation_points,
            "collection_status": "FAILED",
            "failed_points_count": 5,
            "total_points_count": 3,
        }
        with pytest.raises(ValidationError, match="cannot exceed"):
            USGSTrailElevationProfile(**profile)

    def test_point_count_mismatch_fails(self, valid_elevation_points):
        """Test that mismatch between elevation_points length and counts fails."""
        profile = {
            "gmaps_location_id": "ChIJtest123",
            "trail_name": "Precipice Trail",
            "park_code": "acad",
            "source": "osm",
            "elevation_points": valid_elevation_points,  # 3 points
            "collection_status": "COMPLETE",
            "failed_points_count": 0,
            "total_points_count": 5,  # Claims 5 total, but only 3 successful
        }
        with pytest.raises(ValidationError, match="doesn't match expected successful"):
            USGSTrailElevationProfile(**profile)

    def test_complete_status_with_failures_fails(self, valid_elevation_points):
        """Test that COMPLETE status with failures fails validation."""
        profile = {
            "gmaps_location_id": "ChIJtest123",
            "trail_name": "Precipice Trail",
            "park_code": "acad",
            "source": "osm",
            "elevation_points": valid_elevation_points,
            "collection_status": "COMPLETE",
            "failed_points_count": 1,  # Has failures but status is COMPLETE
            "total_points_count": 4,
        }
        with pytest.raises(ValidationError, match=r"COMPLETE.*but.*points failed"):
            USGSTrailElevationProfile(**profile)

    def test_failed_status_with_low_failure_rate_fails(self, valid_elevation_points):
        """Test that FAILED status with low failure rate fails validation."""
        profile = {
            "gmaps_location_id": "ChIJtest123",
            "trail_name": "Precipice Trail",
            "park_code": "acad",
            "source": "osm",
            "elevation_points": valid_elevation_points,  # 3 successful
            "collection_status": "FAILED",
            "failed_points_count": 1,  # Only 25% failure rate
            "total_points_count": 4,
        }
        with pytest.raises(ValidationError, match=r"FAILED.*but failure rate"):
            USGSTrailElevationProfile(**profile)

    def test_empty_elevation_points_with_failed_status(self):
        """Test that empty elevation_points with FAILED status is valid."""
        profile = {
            "gmaps_location_id": "ChIJtest123",
            "trail_name": "Precipice Trail",
            "park_code": "acad",
            "source": "osm",
            "elevation_points": [],
            "collection_status": "FAILED",
            "failed_points_count": 10,
            "total_points_count": 10,
        }
        validated = USGSTrailElevationProfile(**profile)
        assert len(validated.elevation_points) == 0
        assert validated.collection_status == "FAILED"

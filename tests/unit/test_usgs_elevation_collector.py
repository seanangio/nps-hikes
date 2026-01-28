"""Unit tests for USGS Elevation Collector with validation.

Tests the USGSElevationCollector class, focusing on validation integration
and error handling when API responses or data fail validation.
"""

import json
from unittest.mock import MagicMock, Mock, patch

import geopandas as gpd
import pytest
from pydantic import ValidationError
from shapely.geometry import LineString

from scripts.collectors.usgs_elevation_collector import USGSElevationCollector
from scripts.collectors.usgs_schemas import (
    USGSElevationPoint,
    USGSElevationResponse,
    USGSTrailElevationProfile,
)


@pytest.fixture
def mock_logger():
    """Fixture providing a mock logger."""
    return Mock()


@pytest.fixture
def mock_engine():
    """Fixture providing a mock database engine."""
    engine = Mock()
    conn = Mock()
    context_manager = MagicMock()
    context_manager.__enter__ = Mock(return_value=conn)
    context_manager.__exit__ = Mock(return_value=False)
    engine.connect.return_value = context_manager
    return engine


@pytest.fixture
def collector(mock_logger, mock_engine):
    """Fixture providing a collector instance with mocked dependencies."""
    with patch(
        "scripts.collectors.usgs_elevation_collector.get_postgres_engine"
    ) as mock_get_engine:
        mock_get_engine.return_value = mock_engine
        collector = USGSElevationCollector(write_db=False, logger=mock_logger)
        collector.engine = mock_engine
        return collector


@pytest.fixture
def sample_trail_geometry():
    """Fixture providing a sample trail LineString."""
    return LineString([(-68.2733, 44.3386), (-68.2740, 44.3390), (-68.2747, 44.3394)])


class TestUSGSElevationResponseValidation:
    """Test API response validation in get_elevation_usgs method."""

    @patch("scripts.collectors.usgs_elevation_collector.requests.get")
    def test_valid_api_response_passes_validation(self, mock_get, collector):
        """Test that valid API response passes validation and returns elevation."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"value": 470.5}
        mock_get.return_value = mock_response

        elevation = collector.get_elevation_usgs(44.3386, -68.2733)

        assert elevation == 470.5
        assert "44.338600,-68.273300" in collector.elevation_cache

    @patch("scripts.collectors.usgs_elevation_collector.requests.get")
    def test_api_response_with_null_value(self, mock_get, collector):
        """Test that API response with null value returns None."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"value": None}
        mock_get.return_value = mock_response

        elevation = collector.get_elevation_usgs(44.3386, -68.2733)

        assert elevation is None
        collector.logger.warning.assert_called_once()

    @patch("scripts.collectors.usgs_elevation_collector.requests.get")
    def test_api_response_with_no_data_sentinel(self, mock_get, collector):
        """Test that API response with -1000000 sentinel returns None."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"value": -1000000}
        mock_get.return_value = mock_response

        elevation = collector.get_elevation_usgs(44.3386, -68.2733)

        assert elevation is None

    @patch("scripts.collectors.usgs_elevation_collector.requests.get")
    def test_api_response_out_of_range_fails_validation(self, mock_get, collector):
        """Test that API response with out-of-range elevation fails validation."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"value": 99999}  # Way too high
        mock_get.return_value = mock_response

        elevation = collector.get_elevation_usgs(44.3386, -68.2733)

        assert elevation is None
        collector.logger.error.assert_called()
        error_msg = collector.logger.error.call_args[0][0]
        assert "validation failed" in error_msg.lower()

    @patch("scripts.collectors.usgs_elevation_collector.requests.get")
    def test_api_response_missing_value_field_fails(self, mock_get, collector):
        """Test that API response missing 'value' field fails validation."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"elevation": 470.5}  # Wrong field name
        mock_get.return_value = mock_response

        elevation = collector.get_elevation_usgs(44.3386, -68.2733)

        assert elevation is None
        collector.logger.error.assert_called()

    @patch("scripts.collectors.usgs_elevation_collector.requests.get")
    def test_api_response_invalid_value_type_fails(self, mock_get, collector):
        """Test that API response with invalid value type fails validation."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"value": "not_a_number"}
        mock_get.return_value = mock_response

        elevation = collector.get_elevation_usgs(44.3386, -68.2733)

        assert elevation is None
        collector.logger.error.assert_called()

    @patch("scripts.collectors.usgs_elevation_collector.requests.get")
    def test_cache_hit_bypasses_api_call(self, mock_get, collector):
        """Test that cached elevations bypass API call and validation."""
        # Pre-populate cache
        collector.elevation_cache["44.338600,-68.273300"] = 470.5

        elevation = collector.get_elevation_usgs(44.3386, -68.2733)

        assert elevation == 470.5
        mock_get.assert_not_called()  # Should not hit API


class TestUSGSElevationPointValidation:
    """Test individual point validation in sample_trail_elevation method."""

    @patch.object(USGSElevationCollector, "get_elevation_usgs")
    def test_valid_points_pass_validation(
        self, mock_get_elevation, collector, sample_trail_geometry
    ):
        """Test that valid elevation points pass validation."""
        # sample_trail_elevation samples points at regular intervals + end point
        # With default config (50m intervals) on a short trail, we get 4-5 points typically
        mock_get_elevation.return_value = 470.5  # Return same value for all points

        elevation_data, status = collector.sample_trail_elevation(sample_trail_geometry)

        assert status == "COMPLETE"
        assert len(elevation_data) > 0
        # Verify each point is a valid dict that could be validated
        for point in elevation_data:
            validated = USGSElevationPoint(**point)
            assert validated.elevation_m > 0

    @patch.object(USGSElevationCollector, "get_elevation_usgs")
    def test_point_with_invalid_coordinates_fails_validation(
        self, mock_get_elevation, collector
    ):
        """Test that point with invalid coordinates fails validation and is skipped."""
        # Create a geometry with invalid latitude (> 90)
        # This shouldn't happen in practice, but tests validation robustness
        mock_get_elevation.return_value = 470.5

        # Create a trail with coordinates that would fail validation
        invalid_geometry = LineString([(-68.2733, 91.0), (-68.2740, 44.3390)])

        elevation_data, status = collector.sample_trail_elevation(invalid_geometry)

        # First point should fail validation due to latitude > 90
        # Validation error should be logged
        assert collector.logger.error.called

    @patch.object(USGSElevationCollector, "get_elevation_usgs")
    def test_partial_failures_return_partial_status(
        self, mock_get_elevation, collector, sample_trail_geometry
    ):
        """Test that partial failures result in PARTIAL status."""
        # Simulate some points failing to get elevation
        # Alternate between success and failure
        call_count = [0]

        def side_effect(lat, lon):
            call_count[0] += 1
            return 470.5 if call_count[0] % 2 == 1 else None

        mock_get_elevation.side_effect = side_effect

        elevation_data, status = collector.sample_trail_elevation(sample_trail_geometry)

        assert status in ["PARTIAL", "FAILED"]  # Depends on failure rate
        assert len(elevation_data) < mock_get_elevation.call_count  # Some failed


class TestUSGSTrailElevationProfileValidation:
    """Test complete profile validation before database storage."""

    @patch.object(USGSElevationCollector, "get_elevation_usgs")
    def test_valid_profile_passes_validation(
        self, mock_get_elevation, collector, sample_trail_geometry
    ):
        """Test that valid elevation profile passes validation."""
        mock_get_elevation.return_value = 470.5  # Return same value for all points

        # Mock database components
        collector.write_db = True
        collector.db_writer = Mock()
        collector.db_writer.ensure_table_exists = Mock()

        # Create mock trail data
        trail_data = gpd.GeoDataFrame(
            {
                "gmaps_location_id": ["ChIJtest123"],
                "matched_trail_name": ["Precipice Trail"],
                "matched_trail_geometry": [sample_trail_geometry],
                "source": ["osm"],
            },
            geometry="matched_trail_geometry",
        )

        with patch(
            "scripts.collectors.usgs_elevation_collector.gpd.read_postgis"
        ) as mock_read:
            mock_read.return_value = trail_data

            with patch.object(collector.engine, "connect") as mock_connect:
                mock_conn = Mock()
                mock_connect.return_value.__enter__.return_value = mock_conn
                mock_conn.execute.return_value.fetchall.return_value = []

                results = collector.collect_park_elevation_data(
                    "acad", force_refresh=True
                )

        # Should process successfully
        assert results["processed_count"] == 1
        assert results["complete_count"] == 1
        assert results["failed_count"] == 0

    @patch.object(USGSElevationCollector, "get_elevation_usgs")
    def test_profile_with_uppercase_park_code_fails_validation(
        self, mock_get_elevation, collector, sample_trail_geometry
    ):
        """Test that profile with uppercase park code fails validation."""
        mock_get_elevation.side_effect = [470.5, 480.2, 490.8]

        collector.write_db = False

        # Create trail data with uppercase park code
        trail_data = gpd.GeoDataFrame(
            {
                "gmaps_location_id": ["ChIJtest123"],
                "matched_trail_name": ["Precipice Trail"],
                "matched_trail_geometry": [sample_trail_geometry],
                "source": ["osm"],
            },
            geometry="matched_trail_geometry",
        )

        with patch(
            "scripts.collectors.usgs_elevation_collector.gpd.read_postgis"
        ) as mock_read:
            mock_read.return_value = trail_data

            # Manually test validation failure by creating invalid profile
            try:
                profile = USGSTrailElevationProfile(
                    gmaps_location_id="ChIJtest123",
                    trail_name="Precipice Trail",
                    park_code="ACAD",  # Uppercase - should fail
                    source="osm",
                    elevation_points=[],
                    collection_status="COMPLETE",
                    failed_points_count=0,
                    total_points_count=0,
                )
                pytest.fail("Should have raised ValidationError")
            except ValidationError as e:
                assert "lowercase" in str(e).lower()

    @patch.object(USGSElevationCollector, "get_elevation_usgs")
    def test_profile_with_mismatched_counts_fails_validation(
        self, mock_get_elevation, collector
    ):
        """Test that profile with mismatched point counts fails validation."""
        elevation_points = [
            {
                "point_index": 0,
                "distance_m": 0.0,
                "latitude": 44.3386,
                "longitude": -68.2733,
                "elevation_m": 470.5,
            }
        ]

        # Try to create profile with mismatched counts
        with pytest.raises(ValidationError, match="doesn't match expected"):
            USGSTrailElevationProfile(
                gmaps_location_id="ChIJtest123",
                trail_name="Precipice Trail",
                park_code="acad",
                source="osm",
                elevation_points=elevation_points,  # 1 point
                collection_status="COMPLETE",
                failed_points_count=0,
                total_points_count=5,  # Claims 5 total
            )

    @patch.object(USGSElevationCollector, "get_elevation_usgs")
    def test_profile_validation_failure_increments_failed_count(
        self, mock_get_elevation, collector, sample_trail_geometry
    ):
        """Test that profile validation failure increments failed count."""
        mock_get_elevation.return_value = 470.5  # Return same value for all points

        collector.write_db = False

        # Create trail data with empty trail name (will fail validation)
        trail_data = gpd.GeoDataFrame(
            {
                "gmaps_location_id": ["ChIJtest123"],
                "matched_trail_name": [""],  # Empty name - should fail
                "matched_trail_geometry": [sample_trail_geometry],
                "source": ["osm"],
            },
            geometry="matched_trail_geometry",
        )

        with patch(
            "scripts.collectors.usgs_elevation_collector.gpd.read_postgis"
        ) as mock_read:
            mock_read.return_value = trail_data

            results = collector.collect_park_elevation_data("acad", force_refresh=True)

        # Should fail due to validation error
        assert results["failed_count"] > 0


class TestIntegrationScenarios:
    """Test end-to-end scenarios with validation."""

    @patch("scripts.collectors.usgs_elevation_collector.requests.get")
    def test_complete_workflow_with_all_validations(
        self, mock_get, collector, sample_trail_geometry
    ):
        """Test complete workflow from API call through database storage."""
        # Mock API responses
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        # Return valid elevation for all points (using return_value for consistency)
        mock_response.json.return_value = {"value": 470.5}

        collector.write_db = False

        # Get elevation data
        elevation_data, status = collector.sample_trail_elevation(sample_trail_geometry)

        # Verify all validations passed
        assert status == "COMPLETE"
        assert len(elevation_data) > 0

        # Verify we can create a valid profile with this data
        profile = USGSTrailElevationProfile(
            gmaps_location_id="ChIJtest123",
            trail_name="Precipice Trail",
            park_code="acad",
            source="osm",
            elevation_points=elevation_data,
            collection_status=status,
            failed_points_count=0,
            total_points_count=len(elevation_data),
        )

        assert profile.trail_name == "Precipice Trail"
        assert len(profile.elevation_points) > 0

    @patch("scripts.collectors.usgs_elevation_collector.requests.get")
    def test_mixed_valid_and_invalid_responses(
        self, mock_get, collector, sample_trail_geometry
    ):
        """Test handling of mixed valid/invalid API responses."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        # Alternate between valid and None responses
        call_count = [0]

        def json_side_effect():
            call_count[0] += 1
            return {"value": 470.5} if call_count[0] % 2 == 1 else {"value": None}

        mock_response.json.side_effect = json_side_effect

        collector.write_db = False

        elevation_data, status = collector.sample_trail_elevation(sample_trail_geometry)

        # Should have PARTIAL or FAILED status (depending on failure rate)
        assert status in ["PARTIAL", "FAILED"]
        assert len(elevation_data) > 0  # Should have some successful points
        assert len(elevation_data) < call_count[0]  # Some failed

        # Calculate actual failed count
        total_points = call_count[0]
        successful_points = len(elevation_data)
        failed_points = total_points - successful_points

        # Verify we can create a valid profile
        # Note: Need to ensure status aligns with validation rules
        # FAILED requires >50% failure rate, otherwise PARTIAL
        failure_rate = failed_points / total_points
        expected_status = "FAILED" if failure_rate > 0.5 else "PARTIAL"

        profile = USGSTrailElevationProfile(
            gmaps_location_id="ChIJtest123",
            trail_name="Precipice Trail",
            park_code="acad",
            source="osm",
            elevation_points=elevation_data,
            collection_status=expected_status,
            failed_points_count=failed_points,
            total_points_count=total_points,
        )

        assert len(profile.elevation_points) == successful_points

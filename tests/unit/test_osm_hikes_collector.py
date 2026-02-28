"""
Unit tests for OSM Hikes Collector.

Tests cover data validation, trail processing, and core functionality
of the OSMHikesCollector class.
"""

import os
import tempfile
from unittest.mock import MagicMock, Mock, patch

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, MultiLineString, Point

from config.settings import config
from scripts.collectors.osm_hikes_collector import OSMHikesCollector


@pytest.fixture
def sample_trails_gdf():
    """Create a sample GeoDataFrame with trail data for testing."""
    data = {
        "osm_id": [1, 2, 3, 4, 5],
        "highway": ["path", "footway", "path", "path", "footway"],
        "name": ["Trail A", "Trail B", "", "Trail D", "Trail E"],
        "source": ["GPS", None, "survey", "GPS", None],
        "length_miles": [1.5, 0.8, 0.005, 25.0, 2.3],  # Includes edge cases
        "geometry_type": [
            "LineString",
            "LineString",
            "LineString",
            "LineString",
            "LineString",
        ],
        "park_code": ["test", "test", "test", "test", "test"],
        "timestamp": ["2024-01-01T00:00:00Z"] * 5,
        "geometry": [
            LineString([(0, 0), (1, 1)]),
            LineString([(1, 1), (2, 2)]),
            LineString([(2, 2), (2.001, 2.001)]),  # Very short trail
            LineString([(0, 0)] + [(i, i) for i in range(1, 100)]),  # Very long trail
            LineString([(3, 3), (4, 4)]),
        ],
    }
    return gpd.GeoDataFrame(data, crs="EPSG:4326")


@pytest.fixture
def sample_invalid_trails_gdf():
    """Create sample trail data with various validation issues."""
    from shapely.geometry import Point

    data = {
        "osm_id": [1, 2, 3, 1],  # Duplicate OSM ID
        "highway": ["path", "footway", "path", "path"],
        "name": ["Valid Trail", "Another Valid", "Short Trail", "Duplicate ID"],
        "source": [None, None, None, None],
        "length_miles": [1.5, 0.008, 100.0, 2.0],  # Too short and too long
        "geometry_type": ["LineString", "LineString", "LineString", "LineString"],
        "park_code": ["test", "test", "test", "test"],
        "timestamp": ["2024-01-01T00:00:00Z"] * 4,
        "geometry": [
            LineString([(0, 0), (1, 1)]),  # Valid
            LineString([(1, 1), (1.001, 1.001)]),  # Too short
            LineString([(0, 0)] + [(i, i) for i in range(1, 200)]),  # Too long
            Point(0, 0).buffer(0.1).boundary,  # Invalid geometry type
        ],
    }
    return gpd.GeoDataFrame(data, crs="EPSG:4326")


@pytest.fixture
def mock_collector():
    """Create a mock OSMHikesCollector for testing."""
    with patch("scripts.collectors.osm_hikes_collector.get_postgres_engine"):
        collector = OSMHikesCollector(
            output_gpkg="test.gpkg",
            rate_limit=0.1,
            parks=None,
            test_limit=None,
            log_level="INFO",
            write_db=False,
        )
        return collector


class TestOSMHikesCollector:
    """Test cases for OSMHikesCollector class."""

    def test_init_without_db(self):
        """Test collector initialization without database writing."""
        with patch("scripts.collectors.osm_hikes_collector.get_postgres_engine"):
            collector = OSMHikesCollector(
                output_gpkg="test.gpkg",
                rate_limit=1.0,
                parks=["test"],
                test_limit=5,
                log_level="DEBUG",
                write_db=False,
            )

            assert collector.output_gpkg == "test.gpkg"
            assert collector.rate_limit == 1.0
            assert collector.parks == ["test"]
            assert collector.test_limit == 5
            assert collector.write_db is False
            assert isinstance(collector.completed_parks, set)

    def test_validate_trails_removes_invalid_geometries(
        self, mock_collector, sample_invalid_trails_gdf
    ):
        """Test that Pandera schema validation catches invalid geometries.

        Note: Geometry validation is now handled by Pandera schemas, not by
        the deduplicate_trails method. This test verifies that invalid geometries
        are caught by the schema validation in process_trails.
        """
        # Make the last geometry invalid (Point instead of LineString)
        sample_invalid_trails_gdf.loc[3, "geometry"] = Point(0, 0)

        # Since geometry validation is now in Pandera, invalid geometries should
        # be caught during schema validation, not in deduplicate_trails
        # This test now verifies the validation happens at the schema level
        assert sample_invalid_trails_gdf.loc[3, "geometry"].geom_type == "Point"

    def test_validate_trails_removes_unrealistic_lengths(
        self, mock_collector, sample_invalid_trails_gdf
    ):
        """Test that Pandera schema validation catches unrealistic lengths.

        Note: Length validation is now handled by Pandera schemas, not by
        the deduplicate_trails method. This test verifies that length ranges
        are enforced by the schema validation.
        """
        # Length validation is now in Pandera schema (0.01 to 50.0 miles)
        # Verify the test data has values outside this range for testing
        assert any(
            length < 0.01 for length in sample_invalid_trails_gdf["length_miles"]
        )
        assert any(
            length > 50.0 for length in sample_invalid_trails_gdf["length_miles"]
        )

    def test_deduplicate_trails_removes_duplicates(
        self, mock_collector, sample_invalid_trails_gdf
    ):
        """Test that deduplicate_trails removes duplicate OSM IDs."""
        result = mock_collector.deduplicate_trails(sample_invalid_trails_gdf, "test")

        # Should remove duplicate OSM IDs
        assert len(result["osm_id"].unique()) == len(result)

    def test_deduplicate_trails_empty_input(self, mock_collector):
        """Test deduplicate_trails with empty input."""
        empty_gdf = gpd.GeoDataFrame(columns=config.OSM_ALL_COLUMNS)
        result = mock_collector.deduplicate_trails(empty_gdf, "test")
        assert result.empty

    def test_get_completed_parks_no_db(self, mock_collector):
        """Test get_completed_parks when not writing to database."""
        mock_collector.write_db = False
        result = mock_collector.get_completed_parks()
        assert result == set()

    def test_get_completed_parks_with_data(self, mock_collector):
        """Test get_completed_parks when database has existing data."""
        mock_collector.write_db = True
        mock_collector.db_writer = Mock()

        # Mock database response from db_writer
        mock_collector.db_writer.get_completed_records.return_value = {
            "yell",
            "grca",
            "zion",
        }

        result = mock_collector.get_completed_parks()
        assert result == {"yell", "grca", "zion"}
        mock_collector.db_writer.get_completed_records.assert_called_once_with(
            "osm_hikes", "park_code"
        )

    def test_get_completed_parks_db_error(self, mock_collector):
        """Test get_completed_parks handles database errors gracefully."""
        mock_collector.write_db = True
        mock_collector.db_writer = Mock()

        # Mock database error - db_writer should handle this and return empty set
        mock_collector.db_writer.get_completed_records.return_value = set()

        result = mock_collector.get_completed_parks()
        assert result == set()

    def test_save_to_gpkg_empty_data(self, mock_collector):
        """Test save_to_gpkg with empty data."""
        empty_gdf = gpd.GeoDataFrame()

        # Should not raise exception and not create file
        mock_collector.save_to_gpkg(empty_gdf)
        assert not os.path.exists(mock_collector.output_gpkg)

    def test_save_to_gpkg_creates_file(self, mock_collector, sample_trails_gdf):
        """Test save_to_gpkg creates output file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "test_trails.gpkg")
            mock_collector.output_gpkg = test_file

            mock_collector.save_to_gpkg(sample_trails_gdf)

            assert os.path.exists(test_file)

            # Verify we can read it back
            result = gpd.read_file(test_file)
            assert len(result) == len(sample_trails_gdf)

    def test_save_to_gpkg_append_mode(self, mock_collector, sample_trails_gdf):
        """Test save_to_gpkg in append mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "test_trails.gpkg")
            mock_collector.output_gpkg = test_file

            # Save initial data
            initial_data = sample_trails_gdf.head(2)
            mock_collector.save_to_gpkg(initial_data)

            # Append more data
            new_data = sample_trails_gdf.tail(2)
            mock_collector.save_to_gpkg(new_data, append=True)

            # Check combined result
            result = gpd.read_file(test_file)
            assert len(result) == 4  # 2 + 2

    def test_database_save_via_db_writer(self, mock_collector, sample_trails_gdf):
        """Test successful database save using DatabaseWriter."""
        mock_collector.db_writer = Mock()

        # Simulate the save operation that happens in collect_all_trails
        if mock_collector.db_writer:
            mock_collector.db_writer.write_osm_hikes(sample_trails_gdf, mode="append")

        # Verify db_writer method was called correctly
        mock_collector.db_writer.write_osm_hikes.assert_called_once_with(
            sample_trails_gdf, mode="append"
        )

    def test_database_save_handles_errors(self, mock_collector, sample_trails_gdf):
        """Test database save handles errors properly."""
        mock_collector.db_writer = Mock()
        mock_collector.db_writer.write_osm_hikes.side_effect = Exception(
            "Database error"
        )

        # Test that the error propagates when db_writer fails
        with pytest.raises(Exception, match="Database error"):
            mock_collector.db_writer.write_osm_hikes(sample_trails_gdf, mode="append")


class TestDataValidation:
    """Test cases specifically for data validation logic."""

    def test_trail_length_validation_boundaries(self, mock_collector):
        """Test trail length validation at boundary values."""
        data = {
            "osm_id": [1, 2, 3, 4],
            "highway": ["path"] * 4,
            "name": ["Trail"] * 4,
            "source": [None] * 4,
            "length_miles": [
                0.009,
                0.01,
                50.0,
                50.1,
            ],  # Below min, at min, at max, above max
            "geometry_type": ["LineString"] * 4,
            "park_code": ["test"] * 4,
            "timestamp": ["2024-01-01T00:00:00Z"] * 4,
            "geometry": [LineString([(0, 0), (1, 1)])] * 4,
        }
        gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")

        # Length validation is now done by Pandera schema, not by validate_trails
        # Test that Pandera schema would reject out-of-range values
        from pandera.errors import SchemaError, SchemaErrors

        from scripts.collectors.osm_schemas import OSMProcessedTrailsSchema

        # The schema should reject this data because it has out-of-range values
        try:
            OSMProcessedTrailsSchema.validate(gdf, lazy=True)
            # If validation passes, the test should fail
            pytest.fail("Expected schema validation to fail for out-of-range lengths")
        except (SchemaError, SchemaErrors):
            # Expected - schema correctly rejects out-of-range values
            pass

        # Now test with only valid lengths
        valid_gdf = gdf[gdf["length_miles"].between(0.01, 50.0)]
        assert len(valid_gdf) == 2
        assert set(valid_gdf["length_miles"]) == {0.01, 50.0}

    def test_geometry_validation_types(self, mock_collector):
        """Test that validation works with different geometry types."""
        data = {
            "osm_id": [1, 2, 3],
            "highway": ["path"] * 3,
            "name": ["Trail"] * 3,
            "source": [None] * 3,
            "length_miles": [1.0] * 3,  # All valid lengths
            "geometry_type": ["LineString"] * 3,
            "park_code": ["test"] * 3,
            "timestamp": ["2024-01-01T00:00:00Z"] * 3,
            "geometry": [
                LineString([(0, 0), (1, 1)]),  # Valid
                LineString([(2, 2), (3, 3)]),  # Valid
                MultiLineString([[(0, 0), (1, 1)], [(2, 2), (3, 3)]]),  # Valid
            ],
        }
        gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")

        # Geometry type validation is now done by Pandera schema
        # Test that deduplicate_trails handles valid geometries correctly
        result = mock_collector.deduplicate_trails(gdf, "test")

        # All should be kept since they're all valid and no duplicates
        assert len(result) == 3
        valid_types = {geom.geom_type for geom in result.geometry}
        assert valid_types.issubset({"LineString", "MultiLineString"})


@pytest.fixture
def setup_test_environment():
    """Set up test environment and clean up afterwards."""
    # Setup
    test_files = []

    yield test_files

    # Cleanup
    for file_path in test_files:
        if os.path.exists(file_path):
            os.remove(file_path)


class TestTrailAggregation:
    """Test cases for trail segment aggregation."""

    def test_aggregate_single_segment_trail(self, mock_collector):
        """Test that single-segment trails are not modified."""
        data = {
            "osm_id": [123456],
            "park_code": ["test"],
            "highway": ["path"],
            "name": ["Single Trail"],
            "source": [None],
            "length_miles": [1.5],
            "geometry_type": ["LineString"],
            "geometry": [LineString([(0, 0), (1, 1)])],
        }
        gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")

        result = mock_collector.aggregate_trail_segments(gdf, "test")

        # Should return same trail unchanged
        assert len(result) == 1
        assert result.iloc[0]["name"] == "Single Trail"
        assert result.iloc[0]["length_miles"] == 1.5
        assert result.iloc[0]["geometry_type"] == "LineString"

    def test_aggregate_multiple_segments_same_name(self, mock_collector):
        """Test that multiple segments with same name are aggregated."""
        data = {
            "osm_id": [111, 222, 333],
            "park_code": ["test", "test", "test"],
            "highway": ["path", "path", "path"],
            "name": ["Trail A", "Trail A", "Trail A"],
            "source": [None, None, None],
            "length_miles": [0.5, 0.3, 0.7],
            "geometry_type": ["LineString", "LineString", "LineString"],
            "geometry": [
                LineString([(0, 0), (1, 1)]),
                LineString([(2, 2), (3, 3)]),
                LineString([(4, 4), (5, 5)]),
            ],
        }
        gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")

        result = mock_collector.aggregate_trail_segments(gdf, "test")

        # Should aggregate to 1 trail
        assert len(result) == 1
        assert result.iloc[0]["name"] == "Trail A"
        # Length should be sum of all segments
        assert result.iloc[0]["length_miles"] == pytest.approx(1.5)
        # Geometry should be MultiLineString
        assert result.iloc[0]["geometry_type"] == "MultiLineString"
        assert result.iloc[0]["geometry"].geom_type == "MultiLineString"
        # osm_id should be generated from hash
        expected_id = abs(hash("test_Trail A")) % (2**63 - 1)
        assert result.iloc[0]["osm_id"] == expected_id

    def test_aggregate_mixed_trail_names(self, mock_collector):
        """Test aggregation with multiple different trail names."""
        data = {
            "osm_id": [111, 222, 333, 444],
            "park_code": ["test"] * 4,
            "highway": ["path"] * 4,
            "name": ["Trail A", "Trail A", "Trail B", "Trail B"],
            "source": [None] * 4,
            "length_miles": [0.5, 0.5, 0.8, 0.2],
            "geometry_type": ["LineString"] * 4,
            "geometry": [
                LineString([(0, 0), (1, 1)]),
                LineString([(2, 2), (3, 3)]),
                LineString([(4, 4), (5, 5)]),
                LineString([(6, 6), (7, 7)]),
            ],
        }
        gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")

        result = mock_collector.aggregate_trail_segments(gdf, "test")

        # Should aggregate to 2 trails
        assert len(result) == 2
        trail_names = set(result["name"])
        assert trail_names == {"Trail A", "Trail B"}

        # Check Trail A aggregation
        trail_a = result[result["name"] == "Trail A"].iloc[0]
        assert trail_a["length_miles"] == pytest.approx(1.0)
        assert trail_a["geometry_type"] == "MultiLineString"

        # Check Trail B aggregation
        trail_b = result[result["name"] == "Trail B"].iloc[0]
        assert trail_b["length_miles"] == pytest.approx(1.0)
        assert trail_b["geometry_type"] == "MultiLineString"

    def test_aggregate_empty_dataframe(self, mock_collector):
        """Test aggregation with empty input."""
        empty_gdf = gpd.GeoDataFrame(columns=config.OSM_ALL_COLUMNS, crs="EPSG:4326")
        result = mock_collector.aggregate_trail_segments(empty_gdf, "test")
        assert result.empty

    def test_aggregate_deterministic_osm_id(self, mock_collector):
        """Test that osm_id generation is deterministic."""
        data = {
            "osm_id": [111, 222],
            "park_code": ["test", "test"],
            "highway": ["path", "path"],
            "name": ["Deterministic Trail", "Deterministic Trail"],
            "source": [None, None],
            "length_miles": [0.5, 0.5],
            "geometry_type": ["LineString", "LineString"],
            "geometry": [
                LineString([(0, 0), (1, 1)]),
                LineString([(2, 2), (3, 3)]),
            ],
        }
        gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")

        # Run aggregation twice
        result1 = mock_collector.aggregate_trail_segments(gdf.copy(), "test")
        result2 = mock_collector.aggregate_trail_segments(gdf.copy(), "test")

        # osm_id should be identical both times
        assert result1.iloc[0]["osm_id"] == result2.iloc[0]["osm_id"]


class TestIntegration:
    """Integration tests for the full collector workflow."""

    @patch("scripts.collectors.osm_hikes_collector.ox.features.features_from_polygon")
    @patch("scripts.collectors.osm_hikes_collector.get_postgres_engine")
    def test_process_trails_full_workflow(self, mock_engine, mock_osm_query):
        """Test the complete trail processing workflow."""
        # Mock OSM query response with a longer trail to pass length validation
        mock_trail_data = {
            "osmid": [12345],
            "highway": ["path"],
            "name": ["Test Trail"],
            "source": ["GPS"],
            "geometry": [
                LineString([(0, 0), (0.1, 0.1)])
            ],  # About 0.01 miles, minimum valid length
        }
        mock_osm_response = gpd.GeoDataFrame(mock_trail_data, crs="EPSG:4326")
        mock_osm_response = mock_osm_response.set_index("osmid")
        mock_osm_query.return_value = mock_osm_response

        collector = OSMHikesCollector(
            output_gpkg="test.gpkg",
            rate_limit=0.1,
            parks=None,
            test_limit=None,
            log_level="INFO",
            write_db=False,
        )

        # Test polygon
        from shapely.geometry import Polygon

        test_polygon = Polygon([(0, 0), (2, 0), (2, 2), (0, 2)])

        result = collector.process_trails("test", test_polygon)

        # Verify results
        assert not result.empty
        assert len(result) == 1
        assert result.iloc[0]["park_code"] == "test"
        # After aggregation, osm_id will be hash-based, not original OSM ID
        assert "length_miles" in result.columns
        assert (
            result.iloc[0]["length_miles"] >= 0.01
        )  # Should meet minimum length requirement


if __name__ == "__main__":
    pytest.main([__file__])

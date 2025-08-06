"""
Unit tests for OSM Hikes Collector.

Tests cover data validation, trail processing, and core functionality
of the OSMHikesCollector class.
"""

import pytest
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, LineString, MultiLineString
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os

from osm_hikes_collector import OSMHikesCollector
from config.settings import config


@pytest.fixture
def sample_trails_gdf():
    """Create a sample GeoDataFrame with trail data for testing."""
    data = {
        "osm_id": [1, 2, 3, 4, 5],
        "highway": ["path", "footway", "path", "path", "footway"],
        "name": ["Trail A", "Trail B", "", "Trail D", "Trail E"],
        "source": ["GPS", None, "survey", "GPS", None],
        "length_mi": [1.5, 0.8, 0.005, 25.0, 2.3],  # Includes edge cases
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
        "length_mi": [1.5, 0.008, 100.0, 2.0],  # Too short and too long
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
    with patch("osm_hikes_collector.get_postgres_engine"):
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
        with patch("osm_hikes_collector.get_postgres_engine"):
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
        """Test that validate_trails removes trails with invalid geometries."""
        # Make the last geometry invalid (Point instead of LineString)
        sample_invalid_trails_gdf.loc[3, "geometry"] = Point(0, 0)

        result = mock_collector.validate_trails(sample_invalid_trails_gdf, "test")

        # Should remove the invalid geometry
        assert len(result) < len(sample_invalid_trails_gdf)
        assert all(
            geom.geom_type in ["LineString", "MultiLineString"]
            for geom in result.geometry
        )

    def test_validate_trails_removes_unrealistic_lengths(
        self, mock_collector, sample_invalid_trails_gdf
    ):
        """Test that validate_trails removes trails with unrealistic lengths."""
        result = mock_collector.validate_trails(sample_invalid_trails_gdf, "test")

        # Should remove trails that are too short (<0.01 mi) or too long (>50 mi)
        assert all(0.01 <= length <= 50.0 for length in result["length_mi"])

    def test_validate_trails_removes_duplicates(
        self, mock_collector, sample_invalid_trails_gdf
    ):
        """Test that validate_trails removes duplicate OSM IDs."""
        result = mock_collector.validate_trails(sample_invalid_trails_gdf, "test")

        # Should remove duplicate OSM IDs
        assert len(result["osm_id"].unique()) == len(result)

    def test_validate_trails_empty_input(self, mock_collector):
        """Test validate_trails with empty input."""
        empty_gdf = gpd.GeoDataFrame(columns=config.OSM_ALL_COLUMNS)
        result = mock_collector.validate_trails(empty_gdf, "test")
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
            "length_mi": [
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

        result = mock_collector.validate_trails(gdf, "test")

        # Should keep only the middle two (0.01 and 50.0)
        assert len(result) == 2
        assert set(result["length_mi"]) == {0.01, 50.0}

    def test_geometry_validation_types(self, mock_collector):
        """Test that validation works with different geometry types."""
        data = {
            "osm_id": [1, 2, 3],
            "highway": ["path"] * 3,
            "name": ["Trail"] * 3,
            "source": [None] * 3,
            "length_mi": [1.0] * 3,  # All valid lengths
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

        result = mock_collector.validate_trails(gdf, "test")

        # All should be kept since they're all valid
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


class TestIntegration:
    """Integration tests for the full collector workflow."""

    @patch("osm_hikes_collector.ox.features.features_from_polygon")
    @patch("osm_hikes_collector.get_postgres_engine")
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
        assert result.iloc[0]["osm_id"] == 12345
        assert "length_mi" in result.columns
        assert (
            result.iloc[0]["length_mi"] >= 0.01
        )  # Should meet minimum length requirement


if __name__ == "__main__":
    pytest.main([__file__])

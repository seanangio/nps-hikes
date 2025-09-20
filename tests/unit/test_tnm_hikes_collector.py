"""
Unit tests for TNM Hikes Collector.

This module tests the TNM Hikes Collector functionality including API queries,
data processing, filtering, aggregation, and database operations.
"""

import os
import tempfile
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

import pytest
import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString, MultiLineString, Polygon
from sqlalchemy import Engine

from scripts.collectors.tnm_hikes_collector import TNMHikesCollector


@pytest.fixture
def sample_tnm_response():
    """Sample TNM API response for testing."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": 1,
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-68.2, 44.3], [-68.1, 44.4]],
                },
                "properties": {
                    "permanentidentifier": "test-id-1",
                    "name": "Test Trail 1",
                    "lengthmiles": 1.5,
                    "trailtype": "Terra Trail",
                    "hikerpedestrian": "Y",
                    "bicycle": "N",
                    "objectid": 123,
                    "sourcefeatureid": "ACAD",
                    "sourceoriginator": "National Park Service",
                    "loaddate": 1628062652000,
                    "packsaddle": "N",
                    "atv": "N",
                    "motorcycle": "N",
                    "ohvover50inches": "N",
                    "snowshoe": "N",
                    "crosscountryski": "N",
                    "dogsled": "N",
                    "snowmobile": "N",
                    "nonmotorizedwatercraft": None,
                    "motorizedwatercraft": None,
                    "primarytrailmaintainer": "NPS",
                    "nationaltraildesignation": "NRT - National Recreation Trail",
                    "networklength": 130.85722672,
                    "shape_Length": 0.0013874761556818573,
                    "sourcedatadecscription": "NPS Trails 11/2019",
                    "globalid": "{9214AB78-FF94-4823-991A-7C5FCDC97459}",
                    "namealternate": None,
                    "trailnumber": None,
                    "trailnumberalternate": None,
                    "sourcedatasetid": "{8AE6A31A-CBFB-4627-8405-196BBE8B3F57}",
                },
            },
            {
                "type": "Feature",
                "id": 2,
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-68.1, 44.4], [-68.0, 44.5]],
                },
                "properties": {
                    "permanentidentifier": "test-id-2",
                    "name": "Test Trail 2",
                    "lengthmiles": 2.0,
                    "trailtype": "Terra Trail",
                    "hikerpedestrian": "Y",
                    "bicycle": "N",
                    "objectid": 124,
                    "sourcefeatureid": "ACAD",
                    "sourceoriginator": "National Park Service",
                    "loaddate": 1628062652000,
                    "packsaddle": "N",
                    "atv": "N",
                    "motorcycle": "N",
                    "ohvover50inches": "N",
                    "snowshoe": "N",
                    "crosscountryski": "N",
                    "dogsled": "N",
                    "snowmobile": "N",
                    "nonmotorizedwatercraft": None,
                    "motorizedwatercraft": None,
                    "primarytrailmaintainer": "NPS",
                    "nationaltraildesignation": None,
                    "networklength": 10.82619288,
                    "shape_Length": 0.12673015598834056,
                    "sourcedatadecscription": "NPS Trails 10/2019",
                    "globalid": "{1B6BBE0B-79B3-41F4-B55A-B9DEF4AAFD30}",
                    "namealternate": None,
                    "trailnumber": None,
                    "trailnumberalternate": None,
                    "sourcedatasetid": "{8AE6A31A-CBFB-4627-8405-196BBE8B3F57}",
                },
            },
            {
                "type": "Feature",
                "id": 3,
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-68.0, 44.5], [-67.9, 44.6]],
                },
                "properties": {
                    "permanentidentifier": "test-id-3",
                    "name": "",  # Unnamed trail
                    "lengthmiles": 0.5,
                    "trailtype": "Terra Trail",
                    "hikerpedestrian": "Y",
                    "bicycle": "N",
                    "objectid": 125,
                    "sourcefeatureid": "ACAD",
                    "sourceoriginator": "National Park Service",
                    "loaddate": 1628062652000,
                    "packsaddle": "N",
                    "atv": "N",
                    "motorcycle": "N",
                    "ohvover50inches": "N",
                    "snowshoe": "N",
                    "crosscountryski": "N",
                    "dogsled": "N",
                    "snowmobile": "N",
                    "nonmotorizedwatercraft": None,
                    "motorizedwatercraft": None,
                    "primarytrailmaintainer": "NPS",
                    "nationaltraildesignation": None,
                    "networklength": 0.10713394,
                    "shape_Length": 0.001667402575503569,
                    "sourcedatadecscription": "NPS Trails 11/2019",
                    "globalid": "{4110579A-4615-476F-B5F9-F3CAD2A4761E}",
                    "namealternate": None,
                    "trailnumber": None,
                    "trailnumberalternate": None,
                    "sourcedatasetid": "{8AE6A31A-CBFB-4627-8405-196BBE8B3F57}",
                },
            },
        ],
    }


@pytest.fixture
def sample_park_boundary():
    """Sample park boundary for testing."""
    polygon = Polygon(
        [(-68.7, 44.0), (-68.0, 44.0), (-68.0, 44.5), (-68.7, 44.5), (-68.7, 44.0)]
    )
    return gpd.GeoDataFrame(
        {
            "park_code": ["acad"],
            "geometry": [polygon],
            "bbox": ["-68.7,44.0,-68.0,44.5"],  # Add bbox column
        },
        crs="EPSG:4326",
    )


@pytest.fixture
def mock_collector():
    """Create a mock TNM collector for testing."""
    with patch("tnm_hikes_collector.get_postgres_engine"), patch(
        "tnm_hikes_collector.DatabaseWriter"
    ):

        collector = TNMHikesCollector(
            output_gpkg="test_output.gpkg",
            rate_limit=0.1,
            parks=["acad"],
            test_limit=1,
            log_level="INFO",
            write_db=False,
        )

        # Mock the engine
        collector.engine = Mock(spec=Engine)

        return collector


class TestTNMHikesCollector:
    """Test cases for TNM Hikes Collector."""

    def test_init(self):
        """Test collector initialization."""
        with patch("tnm_hikes_collector.get_postgres_engine"), patch(
            "tnm_hikes_collector.DatabaseWriter"
        ):

            collector = TNMHikesCollector(
                output_gpkg="test.gpkg",
                rate_limit=1.0,
                parks=["acad"],
                test_limit=5,
                log_level="DEBUG",
                write_db=True,
            )

            assert collector.output_gpkg == "test.gpkg"
            assert collector.rate_limit == 1.0
            assert collector.parks == ["acad"]
            assert collector.test_limit == 5
            assert collector.write_db is True

    @patch("requests.get")
    def test_query_tnm_api_success(self, mock_get, mock_collector):
        """Test successful TNM API query."""
        # Mock successful response
        mock_response = Mock()
        mock_response.json.return_value = {"features": []}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        bbox_string = "-68.7,44.0,-68.0,44.5"
        response = mock_collector.query_tnm_api(bbox_string, "acad")

        assert response == {"features": []}
        mock_get.assert_called_once()

    @patch("requests.get")
    def test_query_tnm_api_failure(self, mock_get, mock_collector):
        """Test TNM API query failure."""
        # Mock failed response
        mock_get.side_effect = Exception("API Error")

        bbox_string = "-68.7,44.0,-68.0,44.5"
        response = mock_collector.query_tnm_api(bbox_string, "acad")

        assert response is None

    def test_load_trails_to_geodataframe(self, mock_collector, sample_tnm_response):
        """Test loading TNM response to GeoDataFrame."""
        gdf = mock_collector.load_trails_to_geodataframe(sample_tnm_response, "acad")

        assert isinstance(gdf, gpd.GeoDataFrame)
        assert len(gdf) == 3
        assert "park_code" in gdf.columns
        assert gdf["park_code"].iloc[0] == "acad"
        assert "permanentidentifier" in gdf.columns
        assert "name" in gdf.columns

    def test_filter_named_trails(self, mock_collector, sample_tnm_response):
        """Test filtering for named trails."""
        gdf = mock_collector.load_trails_to_geodataframe(sample_tnm_response, "acad")
        filtered_gdf = mock_collector.filter_named_trails(gdf, "acad")

        # Should filter out the unnamed trail (empty name)
        assert len(filtered_gdf) == 2
        assert all(filtered_gdf["name"].notna() & (filtered_gdf["name"] != ""))

    def test_clip_trails_to_boundary(
        self, mock_collector, sample_tnm_response, sample_park_boundary
    ):
        """Test clipping trails to park boundary."""
        trails_gdf = mock_collector.load_trails_to_geodataframe(
            sample_tnm_response, "acad"
        )
        clipped_gdf = mock_collector.clip_trails_to_boundary(
            trails_gdf, sample_park_boundary, "acad"
        )

        # All trails should be within the boundary in this test
        assert len(clipped_gdf) == 3

    def test_aggregate_trails_by_name(self, mock_collector, sample_tnm_response):
        """Test trail aggregation by name."""
        gdf = mock_collector.load_trails_to_geodataframe(sample_tnm_response, "acad")

        # Add a duplicate trail with same name
        duplicate_trail = gdf.iloc[0].copy()
        duplicate_trail["permanentidentifier"] = "test-id-1b"
        # Create a new GeoDataFrame with the duplicate trail
        duplicate_gdf = gpd.GeoDataFrame([duplicate_trail], crs=gdf.crs)
        # Concatenate the two GeoDataFrames
        gdf = gpd.GeoDataFrame(
            pd.concat([gdf, duplicate_gdf], ignore_index=True), crs=gdf.crs
        )

        aggregated_gdf = mock_collector.aggregate_trails_by_name(gdf, "acad")

        # Should aggregate trails with same name
        assert len(aggregated_gdf) <= len(gdf)

    def test_filter_by_minimum_length(self, mock_collector, sample_tnm_response):
        """Test filtering by minimum length."""
        gdf = mock_collector.load_trails_to_geodataframe(sample_tnm_response, "acad")

        # Add a very short trail
        short_trail = gdf.iloc[0].copy()
        short_trail["permanentidentifier"] = "test-id-short"
        short_trail["lengthmiles"] = 0.005  # Below minimum
        # Create a new GeoDataFrame with the short trail
        short_gdf = gpd.GeoDataFrame([short_trail], crs=gdf.crs)
        # Concatenate the two GeoDataFrames
        gdf = gpd.GeoDataFrame(
            pd.concat([gdf, short_gdf], ignore_index=True), crs=gdf.crs
        )

        filtered_gdf = mock_collector.filter_by_minimum_length(gdf, "acad")

        # Should filter out the short trail
        assert len(filtered_gdf) < len(gdf)
        assert all(filtered_gdf["lengthmiles"] >= 0.01)

    def test_add_metadata(self, mock_collector, sample_tnm_response):
        """Test adding metadata to trails."""
        gdf = mock_collector.load_trails_to_geodataframe(sample_tnm_response, "acad")
        gdf_with_metadata = mock_collector.add_metadata(gdf, "acad")

        assert "geometry_type" in gdf_with_metadata.columns
        assert "timestamp" in gdf_with_metadata.columns
        assert "park_code" in gdf_with_metadata.columns
        assert gdf_with_metadata["park_code"].iloc[0] == "acad"

    @patch("tnm_hikes_collector.gpd.read_postgis")
    def test_load_park_boundaries(self, mock_read_postgis, mock_collector):
        """Test loading park boundaries from database."""
        # Mock database response
        mock_gdf = gpd.GeoDataFrame(
            {
                "park_code": ["acad", "yell"],
                "geometry": [
                    Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
                    Polygon([(1, 1), (2, 1), (2, 2), (1, 2)]),
                ],
            },
            crs="EPSG:4326",
        )
        mock_read_postgis.return_value = mock_gdf

        result = mock_collector.load_park_boundaries()

        assert isinstance(result, gpd.GeoDataFrame)
        # The collector filters by parks=['acad'], so only acad should be returned
        assert len(result) == 1
        assert result["park_code"].iloc[0] == "acad"
        mock_read_postgis.assert_called_once()

    def test_get_completed_parks_no_db(self, mock_collector):
        """Test getting completed parks when not writing to DB."""
        mock_collector.write_db = False
        completed = mock_collector.get_completed_parks()

        assert completed == set()

    @patch("tnm_hikes_collector.gpd.read_file")
    def test_save_to_gpkg_new_file(self, mock_read_file, mock_collector):
        """Test saving to new GeoPackage file."""
        # Create a real GeoDataFrame for testing
        test_gdf = gpd.GeoDataFrame(
            {
                "name": ["Trail 1", "Trail 2"],
                "geometry": [
                    LineString([(0, 0), (1, 1)]),
                    LineString([(1, 1), (2, 2)]),
                ],
            },
            crs="EPSG:4326",
        )

        with patch("os.path.exists", return_value=False), patch.object(
            test_gdf, "to_file"
        ) as mock_to_file:
            mock_collector.save_to_gpkg(test_gdf, append=False)

            # Should call to_file on the GeoDataFrame
            mock_to_file.assert_called_once()

    def test_process_trails_full_pipeline(self, mock_collector, sample_park_boundary):
        """Test the complete trail processing pipeline."""
        with patch.object(mock_collector, "query_tnm_api") as mock_query, patch.object(
            mock_collector, "load_trails_to_geodataframe"
        ) as mock_load, patch.object(
            mock_collector, "filter_named_trails"
        ) as mock_filter, patch.object(
            mock_collector, "clip_trails_to_boundary"
        ) as mock_clip, patch.object(
            mock_collector, "aggregate_trails_by_name"
        ) as mock_aggregate, patch.object(
            mock_collector, "filter_by_minimum_length"
        ) as mock_length_filter, patch.object(
            mock_collector, "add_metadata"
        ) as mock_metadata:

            # Mock responses
            mock_query.return_value = {
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[0, 0], [1, 1]],
                        },
                        "properties": {"name": "Test"},
                    }
                ]
            }
            mock_load.return_value = gpd.GeoDataFrame(
                {"name": ["Test Trail"], "geometry": [LineString([(0, 0), (1, 1)])]},
                crs="EPSG:4326",
            )
            mock_filter.return_value = gpd.GeoDataFrame(
                {"name": ["Test Trail"], "geometry": [LineString([(0, 0), (1, 1)])]},
                crs="EPSG:4326",
            )
            mock_clip.return_value = gpd.GeoDataFrame(
                {"name": ["Test Trail"], "geometry": [LineString([(0, 0), (1, 1)])]},
                crs="EPSG:4326",
            )
            mock_aggregate.return_value = gpd.GeoDataFrame(
                {"name": ["Test Trail"], "geometry": [LineString([(0, 0), (1, 1)])]},
                crs="EPSG:4326",
            )
            mock_length_filter.return_value = gpd.GeoDataFrame(
                {"name": ["Test Trail"], "geometry": [LineString([(0, 0), (1, 1)])]},
                crs="EPSG:4326",
            )
            mock_metadata.return_value = gpd.GeoDataFrame(
                {"name": ["Test Trail"], "geometry": [LineString([(0, 0), (1, 1)])]},
                crs="EPSG:4326",
            )

            result = mock_collector.process_trails("acad", sample_park_boundary)

            # Verify all methods were called
            mock_query.assert_called_once()
            mock_load.assert_called_once()
            mock_filter.assert_called_once()
            mock_clip.assert_called_once()
            mock_aggregate.assert_called_once()
            mock_length_filter.assert_called_once()
            mock_metadata.assert_called_once()


class TestDataValidation:
    """Test cases for data validation logic."""

    def test_trail_length_validation(self, mock_collector):
        """Test trail length validation."""
        # Create test data with various lengths
        data = {
            "permanentidentifier": ["id1", "id2", "id3", "id4"],
            "name": ["Trail"] * 4,
            "lengthmiles": [
                0.005,
                0.01,
                50.0,
                50.1,
            ],  # Below min, at min, at max, above max
            "geometry": [LineString([(0, 0), (1, 1)])] * 4,
        }
        gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")

        result = mock_collector.filter_by_minimum_length(gdf, "test")

        # Should keep only trails >= 0.01 miles
        assert len(result) == 3
        assert set(result["lengthmiles"]) == {0.01, 50.0, 50.1}

    def test_geometry_validation_types(self, mock_collector):
        """Test that validation works with different geometry types."""
        data = {
            "permanentidentifier": ["id1", "id2", "id3"],
            "name": ["Trail"] * 3,
            "lengthmiles": [1.0] * 3,
            "geometry": [
                LineString([(0, 0), (1, 1)]),
                LineString([(2, 2), (3, 3)]),
                MultiLineString([[(0, 0), (1, 1)], [(2, 2), (3, 3)]]),
            ],
        }
        gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")

        result = mock_collector.add_metadata(gdf, "test")

        # All should be processed successfully
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

    @patch("tnm_hikes_collector.requests.get")
    @patch("tnm_hikes_collector.get_postgres_engine")
    def test_process_trails_full_workflow(self, mock_engine, mock_requests_get):
        """Test the complete trail processing workflow."""
        # Mock TNM API response
        mock_response = Mock()
        mock_response.json.return_value = {
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[-68.2, 44.3], [-68.1, 44.4]],
                    },
                    "properties": {
                        "permanentidentifier": "test-id-1",
                        "name": "Test Trail",
                        "lengthmiles": 1.5,
                        "trailtype": "Terra Trail",
                        "hikerpedestrian": "Y",
                    },
                }
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_requests_get.return_value = mock_response

        # Mock database
        mock_engine_instance = Mock(spec=Engine)
        mock_engine.return_value = mock_engine_instance

        # Create collector
        with patch("tnm_hikes_collector.DatabaseWriter"):
            collector = TNMHikesCollector(
                output_gpkg="test_output.gpkg",
                rate_limit=0.1,
                parks=["acad"],
                test_limit=1,
                log_level="INFO",
                write_db=False,
            )

            # Mock park boundary
            boundary = gpd.GeoDataFrame(
                {
                    "park_code": ["acad"],
                    "geometry": [
                        Polygon(
                            [
                                (-68.7, 44.0),
                                (-68.0, 44.0),
                                (-68.0, 44.5),
                                (-68.7, 44.5),
                                (-68.7, 44.0),
                            ]
                        )
                    ],
                    "bbox": ["-68.7,44.0,-68.0,44.5"],  # Add bbox column
                },
                crs="EPSG:4326",
            )

            # Process trails
            result = collector.process_trails("acad", boundary)

            # Verify result
            assert isinstance(result, gpd.GeoDataFrame)
            assert len(result) > 0


if __name__ == "__main__":
    pytest.main([__file__])

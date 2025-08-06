import pytest
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from unittest.mock import Mock, patch


class TestNPSDataCollector:

    def test_validate_coordinates_valid_input(self, collector):
        """Test coordinate validation with valid inputs."""
        lat, lon = collector._validate_coordinates("36.1085", "-115.1777", "Test Park")
        assert lat == 36.1085
        assert lon == -115.1777

    def test_validate_coordinates_invalid_latitude(self, collector):
        """Test coordinate validation with invalid latitude."""
        lat, lon = collector._validate_coordinates("91", "-115.1777", "Test Park")
        assert lat is None
        assert lon is None

    def test_validate_coordinates_invalid_format(self, collector):
        """Test coordinate validation with non-numeric input."""
        lat, lon = collector._validate_coordinates(
            "not_a_number", "-115.1777", "Test Park"
        )
        assert lat is None
        assert lon is None

    def test_find_best_park_match_exact_match(self, collector):
        """Test park matching with exact fullName match."""
        mock_results = [
            {
                "fullName": "Zion National Park",
                "parkCode": "zion",
                "relevanceScore": 80,
            },
            {"fullName": "Other Park", "parkCode": "other", "relevanceScore": 100},
        ]

        match = collector._find_best_park_match(
            mock_results, "Zion National Park", "Zion"
        )

        assert match["parkCode"] == "zion"
        assert match["fullName"] == "Zion National Park"

    def test_find_best_park_match_relevance_fallback(self, collector):
        """Test park matching falls back to highest relevance when no exact match."""
        mock_results = [
            {"fullName": "Some Other Park", "parkCode": "other", "relevanceScore": 100},
            {
                "fullName": "Lower Relevance Park",
                "parkCode": "lower",
                "relevanceScore": 80,
            },
        ]

        match = collector._find_best_park_match(
            mock_results, "Nonexistent Park", "Nonexistent"
        )

        # Should pick the first one (highest relevance due to pre-sorting)
        assert match["parkCode"] == "other"
        assert match["relevanceScore"] == 100

    def test_extract_park_data_complete_data(self, collector, sample_csv_row):
        """Test data extraction with complete API response."""
        mock_api_data = {
            "parkCode": "zion",
            "fullName": "Zion National Park",
            "states": "UT",
            "url": "https://www.nps.gov/zion/",
            "latitude": "37.2982022",
            "longitude": "-113.026505",
            "description": "Test description",
        }

        result = collector.extract_park_data(mock_api_data, sample_csv_row)

        assert result["park_name"] == "Zion"
        assert result["visit_month"] == "June"
        assert result["visit_year"] == 2024
        assert result["park_code"] == "zion"
        assert result["full_name"] == "Zion National Park"
        assert result["latitude"] == 37.2982022
        assert result["longitude"] == -113.026505

    def test_extract_park_data_missing_coordinates(self, collector, sample_csv_row):
        """Test data extraction when coordinates are missing."""
        mock_api_data = {
            "parkCode": "test",
            "fullName": "Test Park",
            "states": "UT",
            "url": "https://test.com",
            "description": "Test description",
            # No latitude/longitude
        }

        result = collector.extract_park_data(mock_api_data, sample_csv_row)

        assert result["latitude"] is None
        assert result["longitude"] is None
        assert result["park_code"] == "test"  # Other fields should still work

    def test_extract_park_data_with_sample_response(
        self, collector, sample_park_api_response, sample_csv_row
    ):
        result = collector.extract_park_data(sample_park_api_response, sample_csv_row)
        assert result["park_code"] == "zion"
        assert result["full_name"] == "Zion National Park"
        assert result["latitude"] == 37.2982022
        assert result["longitude"] == -113.026505

    def test_transform_boundary_data_with_sample_response(
        self, collector, sample_boundary_api_response
    ):
        result = collector.transform_boundary_data(sample_boundary_api_response, "zion")
        assert result["park_code"] == "zion"
        assert result["geometry"] is not None
        assert result["geometry_type"] == "Polygon"

    def test_deduplicate_and_aggregate_parks(self, collector, sample_parks_dataframe):
        result = collector._deduplicate_and_aggregate_parks(sample_parks_dataframe)
        assert isinstance(result, pd.DataFrame)
        assert set(result["park_name"]) == {"Zion", "Yosemite", "Yellowstone"}

    def test_extract_valid_park_codes_handles_duplicates_and_missing(self, collector):
        # Create a DataFrame with valid, duplicate, empty, and null park codes
        df = pd.DataFrame(
            {
                "park_code": ["zion", "yose", "zion", "", None, "yellow"],
                "other_col": [1, 2, 3, 4, 5, 6],
            }
        )

        codes = collector._extract_valid_park_codes(df)

        # Should only return unique, non-empty, non-null codes
        assert set(codes) == {"zion", "yose", "yellow"}
        assert len(codes) == 3

    def test_query_park_api_returns_expected_data(
        self, collector, sample_park_api_response
    ):
        # Patch the requests.Session.get method used inside query_park_api
        with patch.object(collector.session, "get") as mock_get:
            # Set up the mock to return a response with our sample data
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"data": [sample_park_api_response]}
            mock_response.headers = {
                "X-RateLimit-Remaining": "100",
                "X-RateLimit-Limit": "1000",
            }
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response

            # Call the method under test
            result = collector.query_park_api("Zion")

            # Assert the result matches the sample data
            assert result["parkCode"] == "zion"
            assert result["fullName"] == "Zion National Park"
            assert result["states"] == "UT"
            assert result["latitude"] == "37.2982022"
            assert result["longitude"] == "-113.026505"

    def test_query_park_boundaries_api_returns_expected_data(
        self, collector, sample_boundary_api_response
    ):
        # Patch the requests.Session.get method used inside query_park_boundaries_api
        with patch.object(collector.session, "get") as mock_get:
            # Set up the mock to return a response with our sample boundary data
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = sample_boundary_api_response
            mock_response.headers = {
                "X-RateLimit-Remaining": "100",
                "X-RateLimit-Limit": "1000",
            }
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response

            # Call the method under test
            result = collector.query_park_boundaries_api("zion")

            # Assert the result matches the sample boundary data
            assert result["type"] == "FeatureCollection"
            assert "features" in result
            assert result["features"][0]["properties"]["parkCode"] == "zion"
            assert result["features"][0]["geometry"]["type"] == "Polygon"

    def test_save_park_results_calls_to_csv(self, collector):
        # Create a small DataFrame
        df = pd.DataFrame(
            {
                "park_name": ["Zion"],
                "visit_month": ["June"],
                "visit_year": [2024],
                "park_code": ["zion"],
                "full_name": ["Zion National Park"],
                "states": ["UT"],
                "url": ["https://www.nps.gov/zion/"],
                "latitude": [37.2982022],
                "longitude": [-113.026505],
                "description": ["Test description"],
                "error_message": [None],
                "collection_status": ["success"],
            }
        )
        with patch.object(df, "to_csv") as mock_to_csv:
            collector.save_park_results(df, "dummy.csv")
            mock_to_csv.assert_called_once_with("dummy.csv", index=False)

    def test_save_boundary_results_calls_to_file(self, collector):
        # Create a small GeoDataFrame
        gdf = gpd.GeoDataFrame(
            {
                "park_code": ["zion"],
                "geometry": [Point(-113.026505, 37.2982022)],
                "geometry_type": ["Point"],
                "boundary_source": ["NPS API"],
                "error_message": [None],
                "collection_status": ["success"],
            },
            geometry="geometry",
            crs="EPSG:4326",
        )
        with patch.object(gdf, "to_file") as mock_to_file:
            collector.save_boundary_results(gdf, "dummy.gpkg")
            mock_to_file.assert_called_once_with("dummy.gpkg", driver="GPKG")

    def test_load_parks_from_csv_happy_path(self, collector):
        # Create a DataFrame that simulates a valid CSV
        df = pd.DataFrame(
            {
                "park_name": ["Zion", "Yosemite"],
                "month": ["June", "July"],
                "year": [2024, 2024],
            }
        )
        with patch("pandas.read_csv", return_value=df) as mock_read_csv:
            result = collector.load_parks_from_csv("dummy.csv")
            mock_read_csv.assert_called_once_with("dummy.csv")
            # Should return the same DataFrame (no rows dropped)
            assert result.equals(df)

    def test_load_parks_from_csv_missing_columns(self, collector):
        # DataFrame missing the 'month' column
        df = pd.DataFrame({"park_name": ["Zion"], "year": [2024]})
        with patch("pandas.read_csv", return_value=df):
            try:
                collector.load_parks_from_csv("dummy.csv")
                assert False, "Should have raised ValueError for missing columns"
            except ValueError as e:
                assert "CSV missing required columns" in str(e)

    def test_load_parks_from_csv_drops_missing_park_names(self, collector):
        # Create a DataFrame with some missing park names
        test_data = {
            "park_name": ["Zion", "", "Grand Canyon", None],
            "month": ["June", "July", "August", "September"],
            "year": [2024, 2024, 2024, 2024],
        }
        df = pd.DataFrame(test_data)

        with patch("pandas.read_csv", return_value=df):
            result = collector.load_parks_from_csv("test.csv")

        # Should drop rows with missing park names
        assert len(result) == 2
        assert "Zion" in result["park_name"].values
        assert "Grand Canyon" in result["park_name"].values

    def test_calculate_bounding_box_valid_geometry(self, collector):
        """Test bounding box calculation with valid geometry."""
        # Create a simple polygon geometry
        geometry = {
            "type": "Polygon",
            "coordinates": [
                [
                    [-68.7, 44.0],
                    [-68.0, 44.0],
                    [-68.0, 44.5],
                    [-68.7, 44.5],
                    [-68.7, 44.0],
                ]
            ],
        }

        bbox_string = collector.calculate_bounding_box(geometry)

        assert bbox_string == "-68.7,44.0,-68.0,44.5"

    def test_calculate_bounding_box_invalid_geometry(self, collector):
        """Test bounding box calculation with invalid geometry."""
        # Invalid geometry that will cause an error
        invalid_geometry = {"type": "Invalid", "coordinates": None}

        bbox_string = collector.calculate_bounding_box(invalid_geometry)

        assert bbox_string is None

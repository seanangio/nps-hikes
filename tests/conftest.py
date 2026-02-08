"""
Shared test fixtures and configuration for the NPS Hikes test suite.

This file contains pytest fixtures that can be used across all test modules.
Fixtures defined here are automatically available to all test files.
"""

import os
from unittest.mock import Mock, patch

import pandas as pd
import pytest
from dotenv import load_dotenv

# Load test environment variables (if any)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


@pytest.fixture
def test_api_key():
    """Provide a test API key for testing."""
    return "test_api_key_12345"


@pytest.fixture
def collector(test_api_key):
    """
    Create a test NPSDataCollector instance.

    This fixture provides a collector instance that can be used across multiple tests.
    The collector uses a test API key and can be mocked for API calls.
    """
    from scripts.collectors.nps_collector import NPSDataCollector

    return NPSDataCollector(test_api_key)


@pytest.fixture
def sample_park_api_response():
    """
    Provide a sample NPS API response for testing.

    This fixture returns a realistic API response that can be used to test
    data extraction and transformation logic.
    """
    return {
        "parkCode": "zion",
        "fullName": "Zion National Park",
        "states": "UT",
        "url": "https://www.nps.gov/zion/",
        "latitude": "37.2982022",
        "longitude": "-113.026505",
        "description": "Zion National Park is a southwest Utah nature preserve.",
        "relevanceScore": 95,
    }


@pytest.fixture
def sample_boundary_api_response():
    """
    Provide a sample boundary API response for testing.

    This fixture returns a realistic boundary API response that can be used
    to test spatial data processing.
    """
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-113.026505, 37.2982022],
                            [-113.026505, 37.2982022],
                            [-113.026505, 37.2982022],
                            [-113.026505, 37.2982022],
                        ]
                    ],
                },
                "properties": {"parkCode": "zion"},
            }
        ],
    }


@pytest.fixture
def sample_csv_row():
    """
    Provide a sample CSV row for testing.

    This fixture returns a pandas Series representing a row from the input CSV
    that can be used to test data processing logic.
    """
    return pd.Series({"park_name": "Zion", "month": "June", "year": 2024})


@pytest.fixture
def sample_parks_dataframe():
    """
    Provide a sample parks DataFrame for testing.

    This fixture returns a small DataFrame with test park data that can be used
    to test data processing and transformation logic.
    """
    return pd.DataFrame(
        {
            "park_name": ["Zion", "Yosemite", "Yellowstone"],
            "month": ["June", "July", "August"],
            "year": [2024, 2024, 2024],
        }
    )


@pytest.fixture
def mock_api_success_response():
    """
    Provide a mock successful API response.

    This fixture returns a Mock object that simulates a successful HTTP response
    from the NPS API.
    """
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [
            {
                "parkCode": "zion",
                "fullName": "Zion National Park",
                "states": "UT",
                "url": "https://www.nps.gov/zion/",
                "latitude": "37.2982022",
                "longitude": "-113.026505",
                "description": "Test description",
                "relevanceScore": 95,
            }
        ]
    }
    mock_response.headers = {
        "X-RateLimit-Remaining": "100",
        "X-RateLimit-Limit": "1000",
    }
    mock_response.raise_for_status.return_value = None
    return mock_response


@pytest.fixture
def mock_api_error_response():
    """
    Provide a mock error API response.

    This fixture returns a Mock object that simulates an error HTTP response
    from the NPS API.
    """
    mock_response = Mock()
    mock_response.status_code = 404
    mock_response.json.return_value = {"error": "Park not found"}
    mock_response.headers = {}
    mock_response.raise_for_status.side_effect = Exception("404 Not Found")
    return mock_response


@pytest.fixture
def test_data_dir():
    """
    Provide the path to the test data directory.

    This fixture returns the path to the test_data directory where test data
    files can be stored and accessed.
    """
    return os.path.join(os.path.dirname(__file__), "test_data")


@pytest.fixture(autouse=True)
def setup_test_environment():
    """
    Set up test environment variables.

    This fixture automatically runs before each test to ensure the test
    environment is properly configured.
    """
    # Set test environment variables if not already set
    if not os.getenv("NPS_API_KEY"):
        os.environ["NPS_API_KEY"] = "test_api_key_12345"

    if not os.getenv("POSTGRES_PASSWORD"):
        os.environ["POSTGRES_PASSWORD"] = "test_password"

    yield

    # Clean up test environment variables after test
    if os.getenv("NPS_API_KEY") == "test_api_key_12345":
        del os.environ["NPS_API_KEY"]

    if os.getenv("POSTGRES_PASSWORD") == "test_password":
        del os.environ["POSTGRES_PASSWORD"]


# API Test Fixtures


@pytest.fixture
def mock_db_engine():
    """
    Provide a mock SQLAlchemy engine for API tests.

    Returns a Mock engine with connection context manager configured.
    Use this to avoid real database connections during API testing.
    """
    from unittest.mock import MagicMock

    mock_engine = MagicMock()
    mock_connection = MagicMock()
    mock_result = MagicMock()

    # Configure connection context manager
    mock_engine.connect.return_value.__enter__.return_value = mock_connection
    mock_engine.connect.return_value.__exit__.return_value = None

    # Configure execute to return mock result
    mock_connection.execute.return_value = mock_result
    mock_result.fetchall.return_value = []

    return mock_engine


@pytest.fixture
def sample_park_trails_response():
    """
    Provide sample data for park trails endpoint testing.

    Returns a dictionary matching the ParkTrailsResponse structure
    with realistic trail data for Yosemite National Park.
    """
    from collections import namedtuple

    Row = namedtuple(
        "Row",
        [
            "osm_id",
            "name",
            "length_miles",
            "highway_type",
            "source",
            "geometry_type",
            "park_name",
            "viz_3d_available",
            "viz_3d_slug",
        ],
    )

    return {
        "rows": [
            Row(
                osm_id=123456789,
                name="Half Dome Trail",
                length_miles=14.2,
                highway_type="path",
                source="osm",
                geometry_type="LineString",
                park_name="Yosemite National Park",
                viz_3d_available=True,
                viz_3d_slug="half_dome_trail",
            ),
            Row(
                osm_id=987654321,
                name="Mist Trail",
                length_miles=6.5,
                highway_type="path",
                source="osm",
                geometry_type="LineString",
                park_name="Yosemite National Park",
                viz_3d_available=False,
                viz_3d_slug=None,
            ),
        ],
        "expected_response": {
            "park_code": "yose",
            "park_name": "Yosemite National Park",
            "trail_count": 2,
            "total_miles": 20.7,
            "trails": [
                {
                    "osm_id": 123456789,
                    "name": "Half Dome Trail",
                    "length_miles": 14.2,
                    "highway_type": "path",
                    "source": "osm",
                    "geometry_type": "LineString",
                    "viz_3d_available": True,
                    "viz_3d_slug": "half_dome_trail",
                },
                {
                    "osm_id": 987654321,
                    "name": "Mist Trail",
                    "length_miles": 6.5,
                    "highway_type": "path",
                    "source": "osm",
                    "geometry_type": "LineString",
                    "viz_3d_available": False,
                    "viz_3d_slug": None,
                },
            ],
        },
    }


@pytest.fixture
def sample_all_trails_response():
    """
    Provide sample data for all trails endpoint testing.

    Returns a dictionary matching the AllTrailsResponse structure
    with realistic trail data from multiple parks and sources.
    """
    from collections import namedtuple

    Row = namedtuple(
        "Row",
        [
            "trail_id",
            "trail_name",
            "park_code",
            "park_name",
            "states",
            "source",
            "length_miles",
            "geometry_type",
            "hiked",
        ],
    )

    return {
        "rows": [
            Row(
                trail_id="550779",
                trail_name="Half Dome Trail",
                park_code="yose",
                park_name="Yosemite National Park",
                states="CA",
                source="TNM",
                length_miles=14.2,
                geometry_type="LineString",
                hiked=True,
            ),
            Row(
                trail_id="123456789",
                trail_name="Mist Trail",
                park_code="yose",
                park_name="Yosemite National Park",
                states="CA",
                source="OSM",
                length_miles=6.5,
                geometry_type="LineString",
                hiked=False,
            ),
        ],
        "expected_response": {
            "trail_count": 2,
            "total_miles": 20.7,
            "trails": [
                {
                    "trail_id": "550779",
                    "trail_name": "Half Dome Trail",
                    "park_code": "yose",
                    "park_name": "Yosemite National Park",
                    "states": "CA",
                    "source": "TNM",
                    "length_miles": 14.2,
                    "geometry_type": "LineString",
                    "hiked": True,
                },
                {
                    "trail_id": "123456789",
                    "trail_name": "Mist Trail",
                    "park_code": "yose",
                    "park_name": "Yosemite National Park",
                    "states": "CA",
                    "source": "OSM",
                    "length_miles": 6.5,
                    "geometry_type": "LineString",
                    "hiked": False,
                },
            ],
        },
    }


@pytest.fixture
def empty_db_result():
    """
    Provide an empty database result for testing no-results scenarios.

    Returns an empty list representing no rows returned from database.
    """
    return []


@pytest.fixture
def sample_parks_response():
    """
    Provide sample data for parks endpoint testing.

    Returns a dictionary with sample park rows that match the parks table schema.
    """
    from collections import namedtuple

    # Row with description (for include_description=true)
    RowWithDescription = namedtuple(
        "RowWithDescription",
        [
            "park_code",
            "park_name",
            "full_name",
            "states",
            "latitude",
            "longitude",
            "url",
            "visit_month",
            "visit_year",
            "description",
        ],
    )

    # Row without description (for include_description=false, default)
    RowWithoutDescription = namedtuple(
        "RowWithoutDescription",
        [
            "park_code",
            "park_name",
            "full_name",
            "states",
            "latitude",
            "longitude",
            "url",
            "visit_month",
            "visit_year",
        ],
    )

    return {
        "rows": [
            RowWithDescription(
                park_code="yose",
                park_name="Yosemite National Park",
                full_name="Yosemite National Park",
                states="CA",
                latitude=37.8651,
                longitude=-119.5383,
                url="https://www.nps.gov/yose/index.htm",
                visit_month="July",
                visit_year=2023,
                description="Not just a great valley, but a shrine to human foresight, the strength of granite, the power of glaciers, the persistence of life, and the tranquility of the High Sierra.",
            ),
            RowWithDescription(
                park_code="zion",
                park_name="Zion National Park",
                full_name="Zion National Park",
                states="UT",
                latitude=37.2982,
                longitude=-113.0265,
                url="https://www.nps.gov/zion/index.htm",
                visit_month="June",
                visit_year=2022,
                description="Follow the paths where ancient native people and pioneers walked. Gaze up at massive sandstone cliffs of cream, pink, and red that soar into a brilliant blue sky.",
            ),
        ],
        "rows_without_description": [
            RowWithoutDescription(
                park_code="yose",
                park_name="Yosemite National Park",
                full_name="Yosemite National Park",
                states="CA",
                latitude=37.8651,
                longitude=-119.5383,
                url="https://www.nps.gov/yose/index.htm",
                visit_month="July",
                visit_year=2023,
            ),
            RowWithoutDescription(
                park_code="zion",
                park_name="Zion National Park",
                full_name="Zion National Park",
                states="UT",
                latitude=37.2982,
                longitude=-113.0265,
                url="https://www.nps.gov/zion/index.htm",
                visit_month="June",
                visit_year=2022,
            ),
        ],
    }


@pytest.fixture
def temp_viz_files(tmp_path):
    """
    Create temporary visualization files for testing.

    Returns paths to temporary static map and elevation matrix files.
    """
    # Create directory structure
    viz_dir = tmp_path / "profiling_results" / "visualizations"
    static_maps_dir = viz_dir / "static_maps"
    elevation_dir = viz_dir / "elevation_changes"

    static_maps_dir.mkdir(parents=True)
    elevation_dir.mkdir(parents=True)

    # Create dummy PNG files
    static_map_path = static_maps_dir / "yose_trails.png"
    elevation_matrix_path = elevation_dir / "yose_elevation_matrix.png"

    # Write minimal PNG header to make it a valid PNG
    png_header = b"\x89PNG\r\n\x1a\n"
    static_map_path.write_bytes(png_header)
    elevation_matrix_path.write_bytes(png_header)

    return {
        "viz_dir": viz_dir,
        "static_map": static_map_path,
        "elevation_matrix": elevation_matrix_path,
        "park_code": "yose",
    }

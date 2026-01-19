"""
Shared test fixtures and configuration for the NPS Hikes test suite.

This file contains pytest fixtures that can be used across all test modules.
Fixtures defined here are automatically available to all test files.
"""

import pytest
import pandas as pd
import os
from unittest.mock import Mock, patch
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

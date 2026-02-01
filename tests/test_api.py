"""
Tests for the NPS Trails API endpoints.

This module contains comprehensive tests for all FastAPI endpoints including:
- Root endpoint
- Park trails endpoint
- All trails endpoint
- Health check endpoint
- Query functions
"""

from collections import namedtuple
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from api.main import app
from api.queries import fetch_all_trails, fetch_trails_for_park

# Create test client
client = TestClient(app)


class TestRootEndpoint:
    """Tests for the root endpoint (GET /)."""

    def test_root_endpoint(self):
        """Test root endpoint returns API information."""
        response = client.get("/")
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "NPS Trails API"
        assert data["version"] == "0.1.0"
        assert "documentation" in data
        assert "endpoints" in data
        assert data["endpoints"]["all_trails"] == "/trails"
        assert data["endpoints"]["trails_by_park"] == "/parks/{park_code}/trails"


class TestParkTrailsEndpoint:
    """Tests for the park trails endpoint (GET /parks/{park_code}/trails)."""

    @patch("api.queries.get_db_engine")
    def test_get_park_trails_success(
        self, mock_get_engine, mock_db_engine, sample_park_trails_response
    ):
        """Test successful retrieval of park trails."""
        # Setup mock
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = sample_park_trails_response["rows"]
        mock_db_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Make request
        response = client.get("/parks/yose/trails")

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["park_code"] == "yose"
        assert data["park_name"] == "Yosemite National Park"
        assert data["trail_count"] == 2
        assert data["total_miles"] == 20.7
        assert len(data["trails"]) == 2
        assert data["trails"][0]["name"] == "Half Dome Trail"

    @patch("api.queries.get_db_engine")
    def test_get_park_trails_with_length_filters(
        self, mock_get_engine, mock_db_engine, sample_park_trails_response
    ):
        """Test park trails endpoint with min and max length filters."""
        # Setup mock
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        # Return only one trail that matches the filter
        mock_result.fetchall.return_value = [sample_park_trails_response["rows"][0]]
        mock_db_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Make request with filters
        response = client.get("/parks/yose/trails?min_length=10&max_length=20")

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["trail_count"] == 1
        assert data["trails"][0]["length_miles"] == 14.2

    @patch("api.queries.get_db_engine")
    def test_get_park_trails_with_trail_type_filter(
        self, mock_get_engine, mock_db_engine, sample_park_trails_response
    ):
        """Test park trails endpoint with trail type filter."""
        # Setup mock
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = sample_park_trails_response["rows"]
        mock_db_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Make request with trail_type filter
        response = client.get("/parks/yose/trails?trail_type=path")

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert all(trail["highway_type"] == "path" for trail in data["trails"])

    @patch("api.queries.get_db_engine")
    def test_get_park_trails_not_found(self, mock_get_engine, mock_db_engine):
        """Test 404 response when park has no trails."""
        # Setup mock to return empty result
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = []
        mock_db_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Make request
        response = client.get("/parks/fake/trails")

        # Assertions
        assert response.status_code == 404
        data = response.json()
        assert "No trails found" in data["detail"]

    def test_get_park_trails_invalid_park_code_format(self):
        """Test validation error for invalid park code format."""
        # Test various invalid formats
        invalid_codes = [
            "YOS",  # Too short
            "YOSEM",  # Too long
            "YOSE",  # Uppercase
            "yo se",  # Contains space
            "123",  # Too short
        ]

        for code in invalid_codes:
            response = client.get(f"/parks/{code}/trails")
            assert response.status_code == 422  # Validation error

    @patch("api.queries.get_db_engine")
    def test_get_park_trails_database_error(self, mock_get_engine):
        """Test 500 error when database query fails."""
        # Setup mock to raise exception
        mock_get_engine.side_effect = Exception("Database connection failed")

        # Make request
        response = client.get("/parks/yose/trails")

        # Assertions
        assert response.status_code == 500
        data = response.json()
        assert "Error retrieving trails" in data["detail"]


class TestAllTrailsEndpoint:
    """Tests for the all trails endpoint (GET /trails)."""

    @patch("api.queries.get_db_engine")
    def test_get_all_trails_no_filters(
        self, mock_get_engine, mock_db_engine, sample_all_trails_response
    ):
        """Test all trails endpoint without filters."""
        # Setup mock
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = sample_all_trails_response["rows"]
        mock_db_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Make request
        response = client.get("/trails")

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["trail_count"] == 2
        assert data["total_miles"] == 20.7
        assert len(data["trails"]) == 2

    @patch("api.queries.get_db_engine")
    def test_get_all_trails_with_length_filters(
        self, mock_get_engine, mock_db_engine, sample_all_trails_response
    ):
        """Test all trails endpoint with min and max length filters."""
        # Setup mock - return only trails matching filter
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = [sample_all_trails_response["rows"][0]]
        mock_db_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Make request
        response = client.get("/trails?min_length=10&max_length=20")

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["trail_count"] == 1
        assert data["trails"][0]["length_miles"] >= 10
        assert data["trails"][0]["length_miles"] <= 20

    @patch("api.queries.get_db_engine")
    def test_get_all_trails_with_park_code(
        self, mock_get_engine, mock_db_engine, sample_all_trails_response
    ):
        """Test all trails endpoint filtered by park code."""
        # Setup mock
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = sample_all_trails_response["rows"]
        mock_db_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Make request
        response = client.get("/trails?park_code=yose")

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert all(trail["park_code"] == "yose" for trail in data["trails"])

    @patch("api.queries.get_db_engine")
    def test_get_all_trails_with_state(
        self, mock_get_engine, mock_db_engine, sample_all_trails_response
    ):
        """Test all trails endpoint filtered by state."""
        # Setup mock
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = sample_all_trails_response["rows"]
        mock_db_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Make request
        response = client.get("/trails?state=CA")

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert all("CA" in trail["states"] for trail in data["trails"])

    @patch("api.queries.get_db_engine")
    def test_get_all_trails_with_source_filter(
        self, mock_get_engine, mock_db_engine, sample_all_trails_response
    ):
        """Test all trails endpoint filtered by source."""
        # Setup mock - return only TNM trails
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = [sample_all_trails_response["rows"][0]]
        mock_db_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Make request
        response = client.get("/trails?source=TNM")

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert all(trail["source"] == "TNM" for trail in data["trails"])

    @patch("api.queries.get_db_engine")
    def test_get_all_trails_with_hiked_status_true(
        self, mock_get_engine, mock_db_engine, sample_all_trails_response
    ):
        """Test all trails endpoint filtered by hiked=true."""
        # Setup mock - return only hiked trails
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = [sample_all_trails_response["rows"][0]]
        mock_db_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Make request
        response = client.get("/trails?hiked=true")

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert all(trail["hiked"] is True for trail in data["trails"])

    @patch("api.queries.get_db_engine")
    def test_get_all_trails_with_hiked_status_false(
        self, mock_get_engine, mock_db_engine, sample_all_trails_response
    ):
        """Test all trails endpoint filtered by hiked=false."""
        # Setup mock - return only non-hiked trails
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = [sample_all_trails_response["rows"][1]]
        mock_db_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Make request
        response = client.get("/trails?hiked=false")

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert all(trail["hiked"] is False for trail in data["trails"])

    @patch("api.queries.get_db_engine")
    def test_get_all_trails_combined_filters(
        self, mock_get_engine, mock_db_engine, sample_all_trails_response
    ):
        """Test all trails endpoint with multiple filters combined."""
        # Setup mock
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = [sample_all_trails_response["rows"][0]]
        mock_db_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Make request with multiple filters
        response = client.get("/trails?state=CA&source=TNM&min_length=10&hiked=true")

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["trail_count"] == 1
        trail = data["trails"][0]
        assert "CA" in trail["states"]
        assert trail["source"] == "TNM"
        assert trail["hiked"] is True
        assert trail["length_miles"] >= 10

    def test_get_all_trails_invalid_state_format(self):
        """Test validation error for invalid state format."""
        # Test various invalid state formats
        invalid_states = [
            "C",  # Too short
            "CAL",  # Too long
            "ca",  # Lowercase
            "C1",  # Contains number
        ]

        for state in invalid_states:
            response = client.get(f"/trails?state={state}")
            assert response.status_code == 422  # Validation error

    def test_get_all_trails_invalid_source(self):
        """Test validation error for invalid source value."""
        # Test invalid source values
        invalid_sources = ["osm", "tnm", "USGS", "invalid"]

        for source in invalid_sources:
            response = client.get(f"/trails?source={source}")
            assert response.status_code == 422  # Validation error

    def test_get_all_trails_invalid_park_code_format(self):
        """Test validation error for invalid park code format in query param."""
        # Test various invalid formats
        invalid_codes = ["YOS", "YOSEM", "YOSE", "yo se"]

        for code in invalid_codes:
            response = client.get(f"/trails?park_code={code}")
            assert response.status_code == 422  # Validation error

    @patch("api.queries.get_db_engine")
    def test_get_all_trails_database_error(self, mock_get_engine):
        """Test 500 error when database query fails."""
        # Setup mock to raise exception
        mock_get_engine.side_effect = Exception("Database connection failed")

        # Make request
        response = client.get("/trails")

        # Assertions
        assert response.status_code == 500
        data = response.json()
        assert "Error retrieving trails" in data["detail"]


class TestHealthEndpoint:
    """Tests for the health check endpoint (GET /health)."""

    @patch("api.main.get_db_engine")
    def test_health_check_healthy(self, mock_get_engine):
        """Test health check returns healthy when database is connected."""
        from unittest.mock import MagicMock

        # Setup mock
        mock_engine = MagicMock()
        mock_connection = MagicMock()
        mock_get_engine.return_value = mock_engine
        mock_engine.connect.return_value.__enter__.return_value = mock_connection
        mock_connection.execute.return_value = MagicMock()

        # Make request
        response = client.get("/health")

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"

    @patch("api.main.get_db_engine")
    def test_health_check_unhealthy(self, mock_get_engine):
        """Test health check returns unhealthy when database connection fails."""
        # Setup mock to raise exception
        mock_get_engine.side_effect = Exception("Connection refused")

        # Make request
        response = client.get("/health")

        # Assertions
        assert response.status_code == 200  # Health endpoint always returns 200
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["database"] == "disconnected"
        assert "error" in data


class TestQueryFunctions:
    """Tests for query functions in api.queries module."""

    @patch("api.queries.get_db_engine")
    def test_fetch_trails_for_park(
        self, mock_get_engine, mock_db_engine, sample_park_trails_response
    ):
        """Test fetch_trails_for_park function directly."""
        # Setup mock
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = sample_park_trails_response["rows"]
        mock_db_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Call function
        result = fetch_trails_for_park(park_code="yose")

        # Assertions
        assert result["park_code"] == "yose"
        assert result["park_name"] == "Yosemite National Park"
        assert result["trail_count"] == 2
        assert result["total_miles"] == 20.7
        assert len(result["trails"]) == 2

    @patch("api.queries.get_db_engine")
    def test_fetch_trails_for_park_with_filters(
        self, mock_get_engine, mock_db_engine, sample_park_trails_response
    ):
        """Test fetch_trails_for_park with filters."""
        # Setup mock
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = [sample_park_trails_response["rows"][0]]
        mock_db_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Call function with filters
        result = fetch_trails_for_park(
            park_code="yose",
            min_length=10.0,
            max_length=20.0,
            trail_type="path",
        )

        # Assertions
        assert result["trail_count"] == 1
        assert result["trails"][0]["length_miles"] == 14.2

    @patch("api.queries.get_db_engine")
    def test_fetch_trails_for_park_empty_result(self, mock_get_engine, mock_db_engine):
        """Test fetch_trails_for_park returns proper structure for empty results."""
        # Setup mock to return empty result
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = []
        mock_db_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Call function
        result = fetch_trails_for_park(park_code="fake")

        # Assertions
        assert result["park_code"] == "fake"
        assert result["park_name"] is None
        assert result["trail_count"] == 0
        assert result["total_miles"] == 0.0
        assert result["trails"] == []

    @patch("api.queries.get_db_engine")
    def test_fetch_all_trails(
        self, mock_get_engine, mock_db_engine, sample_all_trails_response
    ):
        """Test fetch_all_trails function directly."""
        # Setup mock
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = sample_all_trails_response["rows"]
        mock_db_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Call function
        result = fetch_all_trails()

        # Assertions
        assert result["trail_count"] == 2
        assert result["total_miles"] == 20.7
        assert len(result["trails"]) == 2

    @patch("api.queries.get_db_engine")
    def test_fetch_all_trails_with_filters(
        self, mock_get_engine, mock_db_engine, sample_all_trails_response
    ):
        """Test fetch_all_trails with various filters."""
        # Setup mock
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = [sample_all_trails_response["rows"][0]]
        mock_db_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Call function with filters
        result = fetch_all_trails(
            min_length=10.0,
            max_length=20.0,
            park_code="yose",
            state="CA",
            source="TNM",
            hiked=True,
        )

        # Assertions
        assert result["trail_count"] == 1
        trail = result["trails"][0]
        assert trail["source"] == "TNM"
        assert trail["hiked"] is True
        assert trail["park_code"] == "yose"

    @patch("api.queries.get_db_engine")
    def test_fetch_all_trails_empty_result(self, mock_get_engine, mock_db_engine):
        """Test fetch_all_trails returns proper structure for empty results."""
        # Setup mock to return empty result
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = []
        mock_db_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Call function
        result = fetch_all_trails()

        # Assertions
        assert result["trail_count"] == 0
        assert result["total_miles"] == 0.0
        assert result["trails"] == []

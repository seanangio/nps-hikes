"""
Tests for the NPS Trails API endpoints.

This module contains comprehensive tests for all FastAPI endpoints including:
- Root endpoint
- Parks endpoint
- Trails endpoint
- Visualization endpoints
- Health check endpoint
- Query functions
"""

from collections import namedtuple
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from api.main import app
from api.queries import fetch_all_parks, fetch_trails

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
        assert data["endpoints"]["parks"] == "/parks"
        assert data["endpoints"]["trails"] == "/trails"


class TestParksEndpoint:
    """Tests for the parks endpoint (GET /parks)."""

    @patch("api.queries.get_db_engine")
    def test_get_all_parks_without_description(
        self, mock_get_engine, mock_db_engine, sample_parks_response
    ):
        """Test parks endpoint without descriptions (default)."""
        # Setup mock - return rows without description column
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = sample_parks_response[
            "rows_without_description"
        ]
        mock_db_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Make request
        response = client.get("/parks")

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["park_count"] == 2
        assert len(data["parks"]) == 2

        # Check first park
        park1 = data["parks"][0]
        assert park1["park_code"] == "yose"
        assert park1["park_name"] == "Yosemite National Park"
        assert park1["states"] == "CA"
        assert park1["latitude"] == 37.8651
        assert park1["longitude"] == -119.5383
        assert park1["url"] == "https://www.nps.gov/yose/index.htm"
        assert park1["visit_month"] == "July"
        assert park1["visit_year"] == 2023
        assert "description" not in park1  # Should not be included by default

    @patch("api.queries.get_db_engine")
    def test_get_all_parks_with_description(
        self, mock_get_engine, mock_db_engine, sample_parks_response
    ):
        """Test parks endpoint with descriptions included."""
        # Setup mock - return rows with description column
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = sample_parks_response["rows"]
        mock_db_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Make request with include_description=true
        response = client.get("/parks?include_description=true")

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["park_count"] == 2
        assert len(data["parks"]) == 2

        # Check that description is included
        park1 = data["parks"][0]
        assert "description" in park1
        assert "shrine to human foresight" in park1["description"]

    @patch("api.queries.get_db_engine")
    def test_get_all_parks_empty_result(self, mock_get_engine, mock_db_engine):
        """Test parks endpoint with no parks in database."""
        # Setup mock to return empty result
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = []
        mock_db_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Make request
        response = client.get("/parks")

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["park_count"] == 0
        assert data["parks"] == []

    @patch("api.queries.get_db_engine")
    def test_get_all_parks_database_error(self, mock_get_engine):
        """Test 500 error when database query fails."""
        # Setup mock to raise exception
        mock_get_engine.side_effect = Exception("Database connection failed")

        # Make request
        response = client.get("/parks")

        # Assertions
        assert response.status_code == 500
        data = response.json()
        assert "Error retrieving parks" in data["detail"]


class TestVisualizationEndpoints:
    """Tests for visualization endpoints (GET /parks/{park_code}/viz/*)."""

    def test_get_static_map_success(self, temp_viz_files, monkeypatch):
        """Test successful retrieval of static map."""
        import api.main

        # Mock the visualization directory to use temp files
        def mock_dirname(path):
            if "api" in str(path):
                return str(temp_viz_files["viz_dir"].parent.parent)
            return str(temp_viz_files["viz_dir"].parent.parent)

        monkeypatch.setattr("os.path.dirname", mock_dirname)

        # Make request
        response = client.get("/parks/yose/viz/static-map")

        # Assertions
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert b"PNG" in response.content  # Check for PNG header

    def test_get_static_map_not_found(self):
        """Test 404 when static map file doesn't exist."""
        # Request for a park that doesn't have a visualization
        response = client.get("/parks/fake/viz/static-map")

        # Assertions
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()
        assert "fake" in data["detail"]

    def test_get_static_map_invalid_park_code(self):
        """Test validation error for invalid park code format."""
        invalid_codes = ["YOS", "YOSEM", "YOSE", "yo se"]

        for code in invalid_codes:
            response = client.get(f"/parks/{code}/viz/static-map")
            assert response.status_code == 422  # Validation error

    def test_get_elevation_matrix_success(self, temp_viz_files, monkeypatch):
        """Test successful retrieval of elevation matrix."""
        import api.main

        # Mock the visualization directory to use temp files
        def mock_dirname(path):
            if "api" in str(path):
                return str(temp_viz_files["viz_dir"].parent.parent)
            return str(temp_viz_files["viz_dir"].parent.parent)

        monkeypatch.setattr("os.path.dirname", mock_dirname)

        # Make request
        response = client.get("/parks/yose/viz/elevation-matrix")

        # Assertions
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert b"PNG" in response.content  # Check for PNG header

    def test_get_elevation_matrix_not_found(self):
        """Test 404 when elevation matrix file doesn't exist."""
        # Request for a park that doesn't have a visualization
        response = client.get("/parks/fake/viz/elevation-matrix")

        # Assertions
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()
        assert "fake" in data["detail"]

    def test_get_elevation_matrix_invalid_park_code(self):
        """Test validation error for invalid park code format."""
        invalid_codes = ["YOS", "YOSEM", "YOSE", "yo se"]

        for code in invalid_codes:
            response = client.get(f"/parks/{code}/viz/elevation-matrix")
            assert response.status_code == 422  # Validation error

    def test_get_trail_3d_viz_with_existing_file(self, tmp_path, monkeypatch):
        """Test successful retrieval of 3D visualization when file exists."""
        from api.main import app

        # Create temp directory structure and HTML file
        viz_dir = tmp_path / "profiling_results" / "visualizations" / "3d_trails"
        viz_dir.mkdir(parents=True)
        html_file = viz_dir / "yose_half_dome_trail_3d.html"
        html_file.write_text("<html><body>Test 3D Viz</body></html>")

        # Mock get_db_engine to return trail info
        mock_engine = MagicMock()
        mock_result = Mock()
        Row = namedtuple("Row", ["trail_name"])
        mock_result.fetchone.return_value = Row(trail_name="Half Dome Trail")
        mock_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Patch the database engine and directory paths
        def mock_get_db_engine():
            return mock_engine

        def mock_dirname(path):
            # Return tmp_path as the project root
            return str(tmp_path)

        monkeypatch.setattr("api.main.get_db_engine", mock_get_db_engine)
        monkeypatch.setattr("api.main.os.path.dirname", mock_dirname)

        # Make request
        response = client.get("/parks/yose/trails/half_dome_trail/viz/3d")

        # Assertions
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"
        assert b"Test 3D Viz" in response.content

    @patch("api.main.get_db_engine")
    @patch("profiling.modules.trail_3d_viz.Trail3DVisualizer")
    @patch("api.main.os.path.exists")
    def test_get_trail_3d_viz_generate_on_demand(
        self, mock_exists, mock_visualizer_class, mock_get_engine, tmp_path
    ):
        """Test on-demand generation of 3D visualization when file doesn't exist."""
        # Setup mock database response
        mock_engine = MagicMock()
        mock_get_engine.return_value = mock_engine
        mock_result = Mock()
        Row = namedtuple("Row", ["trail_name"])
        mock_result.fetchone.return_value = Row(trail_name="Half Dome Trail")
        mock_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Create temp HTML file that will be "generated"
        html_file = tmp_path / "yose_half_dome_trail_3d.html"

        # Mock visualizer
        mock_visualizer = Mock()
        mock_visualizer_class.return_value = mock_visualizer

        def create_viz_side_effect(park_code, trail_name, z_exaggeration):
            # Simulate file creation
            html_file.write_text("<html><body>Generated 3D Viz</body></html>")
            return str(html_file)

        mock_visualizer.create_3d_visualization = Mock(
            side_effect=create_viz_side_effect
        )

        # File doesn't exist initially, but does after generation
        mock_exists.side_effect = [False, True]

        # Make request with custom z_scale
        response = client.get("/parks/yose/trails/half_dome_trail/viz/3d?z_scale=10.0")

        # Assertions
        assert response.status_code == 200
        assert b"Generated 3D Viz" in response.content

        # Verify visualizer was called with correct parameters
        mock_visualizer.create_3d_visualization.assert_called_once_with(
            park_code="yose", trail_name="Half Dome Trail", z_exaggeration=10.0
        )

    @patch("api.queries.get_db_engine")
    def test_get_trail_3d_viz_trail_not_found(self, mock_get_engine, mock_db_engine):
        """Test 404 when trail doesn't exist or has no elevation data."""
        # Setup mock database response (no trail found)
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchone.return_value = None
        mock_db_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Make request
        response = client.get("/parks/yose/trails/nonexistent_trail/viz/3d")

        # Assertions
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()
        assert "nonexistent_trail" in data["detail"]

    @patch("api.main.get_db_engine")
    @patch("profiling.modules.trail_3d_viz.Trail3DVisualizer")
    @patch("api.main.os.path.exists")
    def test_get_trail_3d_viz_generation_fails(
        self, mock_exists, mock_visualizer_class, mock_get_engine
    ):
        """Test 500 error when visualization generation fails."""
        # Setup mock database response
        mock_engine = MagicMock()
        mock_get_engine.return_value = mock_engine
        mock_result = Mock()
        Row = namedtuple("Row", ["trail_name"])
        mock_result.fetchone.return_value = Row(trail_name="Half Dome Trail")
        mock_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Mock visualizer to return None (failed generation)
        mock_visualizer = Mock()
        mock_visualizer_class.return_value = mock_visualizer
        mock_visualizer.create_3d_visualization.return_value = None

        # Mock file not existing (both before and after generation attempt)
        mock_exists.return_value = False

        # Make request
        response = client.get("/parks/yose/trails/half_dome_trail/viz/3d")

        # Assertions
        assert response.status_code == 500
        data = response.json()
        assert "failed" in data["detail"].lower()

    def test_get_trail_3d_viz_invalid_park_code(self):
        """Test validation error for invalid park code format."""
        invalid_codes = ["YOS", "YOSEM", "YOSE", "yo se"]

        for code in invalid_codes:
            response = client.get(f"/parks/{code}/trails/test_trail/viz/3d")
            assert response.status_code == 422  # Validation error

    def test_get_trail_3d_viz_invalid_trail_slug(self):
        """Test validation error for invalid trail slug format."""
        # Use URL-encoded invalid slugs that FastAPI can't parse according to pattern
        # Note: spaces get URL encoded to %20, so we need patterns that truly violate the regex
        invalid_slugs = ["UPPERCASE", "trail.name", "trail@name", ""]

        for slug in invalid_slugs:
            response = client.get(f"/parks/yose/trails/{slug}/viz/3d")
            # Empty slug gives 404, others give 422
            assert response.status_code in [404, 422]

    def test_get_trail_3d_viz_z_scale_validation(self):
        """Test z_scale parameter validation."""
        # Test z_scale below minimum (1.0)
        response = client.get("/parks/yose/trails/test_trail/viz/3d?z_scale=0.5")
        assert response.status_code == 422

        # Test z_scale above maximum (20.0)
        response = client.get("/parks/yose/trails/test_trail/viz/3d?z_scale=25.0")
        assert response.status_code == 422


class TestTrailsEndpoint:
    """Tests for the trails endpoint (GET /trails)."""

    @patch("api.queries.get_db_engine")
    def test_get_trails_no_filters(
        self, mock_get_engine, mock_db_engine, sample_trails_response
    ):
        """Test trails endpoint without filters."""
        # Setup mock
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = sample_trails_response["rows"]
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
    def test_get_trails_with_length_filters(
        self, mock_get_engine, mock_db_engine, sample_trails_response
    ):
        """Test trails endpoint with min and max length filters."""
        # Setup mock - return only trails matching filter
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = [sample_trails_response["rows"][0]]
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
    def test_get_trails_with_park_code(
        self, mock_get_engine, mock_db_engine, sample_trails_response
    ):
        """Test trails endpoint filtered by park code."""
        # Setup mock
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = sample_trails_response["rows"]
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
    def test_get_trails_with_state(
        self, mock_get_engine, mock_db_engine, sample_trails_response
    ):
        """Test trails endpoint filtered by state."""
        # Setup mock
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = sample_trails_response["rows"]
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
    def test_get_trails_with_source_filter(
        self, mock_get_engine, mock_db_engine, sample_trails_response
    ):
        """Test trails endpoint filtered by source."""
        # Setup mock - return only TNM trails
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = [sample_trails_response["rows"][0]]
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
    def test_get_trails_with_hiked_status_true(
        self, mock_get_engine, mock_db_engine, sample_trails_response
    ):
        """Test trails endpoint filtered by hiked=true."""
        # Setup mock - return only hiked trails
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = [sample_trails_response["rows"][0]]
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
    def test_get_trails_with_hiked_status_false(
        self, mock_get_engine, mock_db_engine, sample_trails_response
    ):
        """Test trails endpoint filtered by hiked=false."""
        # Setup mock - return only non-hiked trails
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = [sample_trails_response["rows"][1]]
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
    def test_get_trails_combined_filters(
        self, mock_get_engine, mock_db_engine, sample_trails_response
    ):
        """Test trails endpoint with multiple filters combined."""
        # Setup mock
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = [sample_trails_response["rows"][0]]
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

    def test_get_trails_invalid_state_format(self):
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

    def test_get_trails_invalid_source(self):
        """Test validation error for invalid source value."""
        # Test invalid source values
        invalid_sources = ["osm", "tnm", "USGS", "invalid"]

        for source in invalid_sources:
            response = client.get(f"/trails?source={source}")
            assert response.status_code == 422  # Validation error

    def test_get_trails_invalid_park_code_format(self):
        """Test validation error for invalid park code format in query param."""
        # Test various invalid formats
        invalid_codes = ["YOS", "YOSEM", "YOSE", "yo se"]

        for code in invalid_codes:
            response = client.get(f"/trails?park_code={code}")
            assert response.status_code == 422  # Validation error

    @patch("api.queries.get_db_engine")
    def test_get_trails_database_error(self, mock_get_engine):
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
    def test_fetch_all_parks_without_description(
        self, mock_get_engine, mock_db_engine, sample_parks_response
    ):
        """Test fetch_all_parks function without descriptions."""
        # Setup mock
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = sample_parks_response[
            "rows_without_description"
        ]
        mock_db_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Call function
        result = fetch_all_parks(include_description=False)

        # Assertions
        assert result["park_count"] == 2
        assert len(result["parks"]) == 2
        assert result["parks"][0]["park_code"] == "yose"
        assert "description" not in result["parks"][0]

    @patch("api.queries.get_db_engine")
    def test_fetch_all_parks_with_description(
        self, mock_get_engine, mock_db_engine, sample_parks_response
    ):
        """Test fetch_all_parks function with descriptions."""
        # Setup mock
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = sample_parks_response["rows"]
        mock_db_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Call function
        result = fetch_all_parks(include_description=True)

        # Assertions
        assert result["park_count"] == 2
        assert len(result["parks"]) == 2
        assert "description" in result["parks"][0]
        assert "shrine to human foresight" in result["parks"][0]["description"]

    @patch("api.queries.get_db_engine")
    def test_fetch_all_parks_empty_result(self, mock_get_engine, mock_db_engine):
        """Test fetch_all_parks returns proper structure for empty results."""
        # Setup mock to return empty result
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = []
        mock_db_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Call function
        result = fetch_all_parks()

        # Assertions
        assert result["park_count"] == 0
        assert result["parks"] == []

    @patch("api.queries.get_db_engine")
    def test_fetch_trails(
        self, mock_get_engine, mock_db_engine, sample_trails_response
    ):
        """Test fetch_trails function without park_code."""
        # Setup mock
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = sample_trails_response["rows"]
        mock_db_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Call function
        result = fetch_trails()

        # Assertions
        assert result["trail_count"] == 2
        assert result["total_miles"] == 20.7
        assert len(result["trails"]) == 2

    @patch("api.queries.get_db_engine")
    def test_fetch_trails_with_filters(
        self, mock_get_engine, mock_db_engine, sample_trails_response
    ):
        """Test fetch_trails with various filters."""
        # Setup mock
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = [sample_trails_response["rows"][0]]
        mock_db_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Call function with filters
        result = fetch_trails(
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
    def test_fetch_trails_empty_result(self, mock_get_engine, mock_db_engine):
        """Test fetch_trails returns proper structure for empty results."""
        # Setup mock to return empty result
        mock_get_engine.return_value = mock_db_engine
        mock_result = Mock()
        mock_result.fetchall.return_value = []
        mock_db_engine.connect.return_value.__enter__.return_value.execute.return_value = (
            mock_result
        )

        # Call function
        result = fetch_trails()

        # Assertions
        assert result["trail_count"] == 0
        assert result["total_miles"] == 0.0
        assert result["trails"] == []

"""
Integration tests for FastAPI → Database integration.

These tests verify that API endpoints correctly query the PostgreSQL database
and return properly formatted responses. Unlike unit tests that mock the database,
these tests use a real test database with seeded data.

Test Strategy:
- Seed test database with known data
- Call API endpoints via TestClient
- Verify responses match database state
- Test filters, pagination, and error handling
- Fast tests (no external API calls)

Run with:
    pytest tests/integration/test_api_db.py -v -m integration
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


@pytest.fixture
def api_client(test_db_writer):
    """
    Create FastAPI test client that uses the test database.

    This fixture patches the database engine to use the test database
    instead of the production database.
    """
    # Import here to avoid loading before fixture setup
    import os
    import sys
    from unittest.mock import patch

    # Import app
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from api.main import app

    # Patch get_db_engine to return test engine
    with (
        patch("api.database.get_db_engine", return_value=test_db_writer.engine),
        patch("api.queries.get_db_engine", return_value=test_db_writer.engine),
    ):
        client = TestClient(app)
        yield client


class TestParksEndpoint:
    """Integration tests for /parks endpoint with database."""

    def test_parks_endpoint_returns_database_data(self, test_db_writer, api_client):
        """
        Test that /parks endpoint returns data from the database.

        Verifies:
        1. Endpoint queries the database
        2. Response includes all seeded parks
        3. Response structure matches Pydantic model
        4. Park metadata is correctly serialized
        """
        # Arrange - Seed database with test parks
        import pandas as pd

        parks_data = {
            "park_code": ["yose", "zion", "grca"],
            "park_name": [
                "Yosemite National Park",
                "Zion National Park",
                "Grand Canyon National Park",
            ],
            "designation": ["National Park", "National Park", "National Park"],
            "states": ["CA", "UT", "AZ"],
            "latitude": [37.8651, 37.2982, 36.1069],
            "longitude": [-119.5383, -113.0265, -112.1129],
            "url": [
                "https://www.nps.gov/yose/index.htm",
                "https://www.nps.gov/zion/index.htm",
                "https://www.nps.gov/grca/index.htm",
            ],
            "visit_month": ["July", "May", None],
            "visit_year": [2023, 2024, None],
            "description": [
                "Yosemite description",
                "Zion description",
                "Grand Canyon description",
            ],
            "collection_status": ["success", "success", "success"],
        }

        parks_df = pd.DataFrame(parks_data)
        test_db_writer.write_parks(parks_df, mode="upsert")

        # Act - Query the API
        response = api_client.get("/parks")

        # Assert - Verify response
        assert response.status_code == 200
        data = response.json()

        assert data["park_count"] == 3
        assert data["visited_count"] == 2  # yose and zion have visit dates
        assert len(data["parks"]) == 3

        # Verify first park details
        yose = next(p for p in data["parks"] if p["park_code"] == "yose")
        assert yose["park_name"] == "Yosemite National Park"
        assert yose["designation"] == "National Park"
        assert yose["states"] == "CA"
        assert yose["latitude"] == 37.8651
        assert yose["longitude"] == -119.5383
        assert yose["visit_month"] == "July"
        assert yose["visit_year"] == 2023
        assert "description" not in yose  # Not included by default

    def test_parks_endpoint_with_description_filter(self, test_db_writer, api_client):
        """Test that include_description=true returns descriptions."""
        # Arrange
        import pandas as pd

        parks_data = {
            "park_code": ["yose"],
            "park_name": ["Yosemite National Park"],
            "designation": ["National Park"],
            "states": ["CA"],
            "latitude": [37.8651],
            "longitude": [-119.5383],
            "url": ["https://www.nps.gov/yose/index.htm"],
            "visit_month": ["July"],
            "visit_year": [2023],
            "description": ["Beautiful park with granite cliffs"],
            "collection_status": ["success"],
        }

        parks_df = pd.DataFrame(parks_data)
        test_db_writer.write_parks(parks_df, mode="upsert")

        # Act
        response = api_client.get("/parks?include_description=true")

        # Assert
        assert response.status_code == 200
        data = response.json()

        park = data["parks"][0]
        assert "description" in park
        assert park["description"] == "Beautiful park with granite cliffs"

    def test_parks_endpoint_with_visited_filter(self, test_db_writer, api_client):
        """Test filtering parks by visited status."""
        # Arrange
        import pandas as pd

        parks_data = {
            "park_code": ["yose", "zion", "grca"],
            "park_name": [
                "Yosemite National Park",
                "Zion National Park",
                "Grand Canyon National Park",
            ],
            "designation": ["National Park", "National Park", "National Park"],
            "states": ["CA", "UT", "AZ"],
            "latitude": [37.8651, 37.2982, 36.1069],
            "longitude": [-119.5383, -113.0265, -112.1129],
            "url": [
                "https://www.nps.gov/yose/index.htm",
                "https://www.nps.gov/zion/index.htm",
                "https://www.nps.gov/grca/index.htm",
            ],
            "visit_month": ["July", None, None],
            "visit_year": [2023, None, None],
            "description": ["Yosemite", "Zion", "Grand Canyon"],
            "collection_status": ["success", "success", "success"],
        }

        parks_df = pd.DataFrame(parks_data)
        test_db_writer.write_parks(parks_df, mode="upsert")

        # Act - Filter for visited parks only
        response = api_client.get("/parks?visited=true")

        # Assert
        assert response.status_code == 200
        data = response.json()

        assert data["park_count"] == 1
        assert data["visited_count"] == 1
        assert data["parks"][0]["park_code"] == "yose"

        # Act - Filter for unvisited parks
        response = api_client.get("/parks?visited=false")

        # Assert
        assert response.status_code == 200
        data = response.json()

        assert data["park_count"] == 2
        assert data["visited_count"] == 0
        park_codes = [p["park_code"] for p in data["parks"]]
        assert "zion" in park_codes
        assert "grca" in park_codes

    def test_parks_endpoint_empty_database(self, api_client):
        """Test that empty database returns empty list, not error."""
        # Act - Query with no parks in database
        response = api_client.get("/parks")

        # Assert
        assert response.status_code == 200
        data = response.json()

        assert data["park_count"] == 0
        assert data["visited_count"] == 0
        assert data["parks"] == []


class TestTrailsEndpoint:
    """Integration tests for /trails endpoint with database."""

    def test_trails_endpoint_returns_database_data(
        self, test_db_writer, api_client, tmp_path
    ):
        """
        Test that /trails endpoint returns trail data from database.

        Verifies:
        1. Endpoint queries osm_hikes and tnm_hikes tables
        2. Trails from both sources are returned
        3. Response structure matches Pydantic model
        """
        # Arrange - Create park first (FK requirement)
        import geopandas as gpd
        import pandas as pd
        from shapely.geometry import LineString

        parks_data = {
            "park_code": ["yose"],
            "park_name": ["Yosemite National Park"],
            "designation": ["National Park"],
            "states": ["CA"],
            "latitude": [37.8651],
            "longitude": [-119.5383],
            "url": ["https://www.nps.gov/yose/index.htm"],
            "visit_month": ["July"],
            "visit_year": [2023],
            "description": ["Yosemite"],
            "collection_status": ["success"],
        }
        parks_df = pd.DataFrame(parks_data)
        test_db_writer.write_parks(parks_df, mode="upsert")

        # Create OSM trails
        osm_data = {
            "osm_id": [123456],
            "park_code": ["yose"],
            "name": ["Half Dome Trail"],
            "highway": ["path"],
            "source": ["OpenStreetMap"],
            "length_miles": [8.2],
            "geometry_type": ["LineString"],
            "geometry": [LineString([(-119.5, 37.8), (-119.51, 37.81)])],
        }
        osm_gdf = gpd.GeoDataFrame(osm_data, crs="EPSG:4326")
        test_db_writer.write_osm_hikes(osm_gdf, mode="append")

        # Create TNM trails
        tnm_data = {
            "permanent_identifier": ["tnm_trail_001"],
            "park_code": ["yose"],
            "name": ["Mist Trail"],
            "trail_type": ["Terra Trail"],
            "hiker_pedestrian": ["Y"],
            "length_miles": [5.4],
            "geometry_type": ["LineString"],
            "geometry": [LineString([(-119.52, 37.82), (-119.53, 37.83)])],
        }
        tnm_gdf = gpd.GeoDataFrame(tnm_data, crs="EPSG:4326")
        test_db_writer.write_tnm_hikes(tnm_gdf, mode="append")

        # Act - Query the API
        response = api_client.get("/trails")

        # Assert - Verify response
        assert response.status_code == 200
        data = response.json()

        assert data["trail_count"] == 2
        assert len(data["trails"]) == 2

        # Verify OSM trail
        half_dome = next((t for t in data["trails"] if t["source"] == "OSM"), None)
        assert half_dome is not None
        assert half_dome["trail_name"] == "Half Dome Trail"
        assert half_dome["length_miles"] == 8.2
        assert half_dome["park_code"] == "yose"

        # Verify TNM trail
        mist_trail = next((t for t in data["trails"] if t["source"] == "TNM"), None)
        assert mist_trail is not None
        assert mist_trail["trail_name"] == "Mist Trail"
        assert mist_trail["length_miles"] == 5.4

    def test_trails_endpoint_with_park_code_filter(self, test_db_writer, api_client):
        """Test filtering trails by park_code."""
        # Arrange - Create 2 parks with trails
        import geopandas as gpd
        import pandas as pd
        from shapely.geometry import LineString

        parks_data = {
            "park_code": ["yose", "zion"],
            "park_name": ["Yosemite National Park", "Zion National Park"],
            "designation": ["National Park", "National Park"],
            "states": ["CA", "UT"],
            "latitude": [37.8651, 37.2982],
            "longitude": [-119.5383, -113.0265],
            "url": [
                "https://www.nps.gov/yose/index.htm",
                "https://www.nps.gov/zion/index.htm",
            ],
            "visit_month": ["July", "May"],
            "visit_year": [2023, 2024],
            "description": ["Yosemite", "Zion"],
            "collection_status": ["success", "success"],
        }
        parks_df = pd.DataFrame(parks_data)
        test_db_writer.write_parks(parks_df, mode="upsert")

        # Create trails for both parks
        osm_data = {
            "osm_id": [1, 2],
            "park_code": ["yose", "zion"],
            "name": ["Half Dome Trail", "Angels Landing"],
            "highway": ["path", "path"],
            "source": ["OpenStreetMap", "OpenStreetMap"],
            "length_miles": [8.2, 5.4],
            "geometry_type": ["LineString", "LineString"],
            "geometry": [
                LineString([(-119.5, 37.8), (-119.51, 37.81)]),
                LineString([(-113.0, 37.2), (-113.01, 37.21)]),
            ],
        }
        osm_gdf = gpd.GeoDataFrame(osm_data, crs="EPSG:4326")
        test_db_writer.write_osm_hikes(osm_gdf, mode="append")

        # Act - Filter by park_code
        response = api_client.get("/trails?park_code=yose")

        # Assert
        assert response.status_code == 200
        data = response.json()

        assert data["trail_count"] == 1
        assert data["trails"][0]["park_code"] == "yose"
        assert data["trails"][0]["trail_name"] == "Half Dome Trail"

    def test_trails_endpoint_with_length_filters(self, test_db_writer, api_client):
        """Test filtering trails by min_length and max_length."""
        # Arrange
        import geopandas as gpd
        import pandas as pd
        from shapely.geometry import LineString

        parks_data = {
            "park_code": ["yose"],
            "park_name": ["Yosemite National Park"],
            "designation": ["National Park"],
            "states": ["CA"],
            "latitude": [37.8651],
            "longitude": [-119.5383],
            "url": ["https://www.nps.gov/yose/index.htm"],
            "visit_month": ["July"],
            "visit_year": [2023],
            "description": ["Yosemite"],
            "collection_status": ["success"],
        }
        parks_df = pd.DataFrame(parks_data)
        test_db_writer.write_parks(parks_df, mode="upsert")

        # Create trails with different lengths
        osm_data = {
            "osm_id": [1, 2, 3],
            "park_code": ["yose", "yose", "yose"],
            "name": ["Short Trail", "Medium Trail", "Long Trail"],
            "highway": ["path", "path", "path"],
            "source": ["OpenStreetMap", "OpenStreetMap", "OpenStreetMap"],
            "length_miles": [2.5, 7.0, 12.5],
            "geometry_type": ["LineString", "LineString", "LineString"],
            "geometry": [
                LineString([(-119.5, 37.8), (-119.51, 37.81)]),
                LineString([(-119.5, 37.8), (-119.52, 37.82)]),
                LineString([(-119.5, 37.8), (-119.55, 37.85)]),
            ],
        }
        osm_gdf = gpd.GeoDataFrame(osm_data, crs="EPSG:4326")
        test_db_writer.write_osm_hikes(osm_gdf, mode="append")

        # Act - Filter for trails 5-10 miles
        response = api_client.get("/trails?min_length=5&max_length=10")

        # Assert
        assert response.status_code == 200
        data = response.json()

        assert data["trail_count"] == 1
        assert data["trails"][0]["trail_name"] == "Medium Trail"
        assert data["trails"][0]["length_miles"] == 7.0

    def test_trails_endpoint_with_source_filter(self, test_db_writer, api_client):
        """Test filtering trails by source (OSM vs TNM)."""
        # Arrange
        import geopandas as gpd
        import pandas as pd
        from shapely.geometry import LineString

        parks_data = {
            "park_code": ["yose"],
            "park_name": ["Yosemite National Park"],
            "designation": ["National Park"],
            "states": ["CA"],
            "latitude": [37.8651],
            "longitude": [-119.5383],
            "url": ["https://www.nps.gov/yose/index.htm"],
            "visit_month": ["July"],
            "visit_year": [2023],
            "description": ["Yosemite"],
            "collection_status": ["success"],
        }
        parks_df = pd.DataFrame(parks_data)
        test_db_writer.write_parks(parks_df, mode="upsert")

        # Create OSM trail
        osm_data = {
            "osm_id": [1],
            "park_code": ["yose"],
            "name": ["OSM Trail"],
            "highway": ["path"],
            "source": ["OpenStreetMap"],
            "length_miles": [5.0],
            "geometry_type": ["LineString"],
            "geometry": [LineString([(-119.5, 37.8), (-119.51, 37.81)])],
        }
        osm_gdf = gpd.GeoDataFrame(osm_data, crs="EPSG:4326")
        test_db_writer.write_osm_hikes(osm_gdf, mode="append")

        # Create TNM trail
        tnm_data = {
            "permanent_identifier": ["tnm_001"],
            "park_code": ["yose"],
            "name": ["TNM Trail"],
            "trail_type": ["Terra Trail"],
            "hiker_pedestrian": ["Y"],
            "length_miles": [6.0],
            "geometry_type": ["LineString"],
            "geometry": [LineString([(-119.52, 37.82), (-119.53, 37.83)])],
        }
        tnm_gdf = gpd.GeoDataFrame(tnm_data, crs="EPSG:4326")
        test_db_writer.write_tnm_hikes(tnm_gdf, mode="append")

        # Act - Filter for TNM only
        response = api_client.get("/trails?source=TNM")

        # Assert
        assert response.status_code == 200
        data = response.json()

        assert data["trail_count"] == 1
        assert data["trails"][0]["source"] == "TNM"
        assert data["trails"][0]["trail_name"] == "TNM Trail"

    def test_trails_endpoint_empty_database(self, api_client):
        """Test that empty trails table returns empty list."""
        # Act
        response = api_client.get("/trails")

        # Assert
        assert response.status_code == 200
        data = response.json()

        assert data["trail_count"] == 0
        assert data["trails"] == []

    def test_trails_endpoint_invalid_park_code(self, api_client):
        """Test that invalid park_code parameter returns 422 validation error."""
        # Act - Use invalid park code (not 4 lowercase letters)
        response = api_client.get("/trails?park_code=INVALID")

        # Assert
        assert response.status_code == 422  # Validation error


class TestHealthEndpoint:
    """Integration tests for /health endpoint."""

    def test_health_check_with_database_connected(self, api_client):
        """Test health endpoint when database is connected."""
        # Act
        response = api_client.get("/health")

        # Assert
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "healthy"
        assert data["database"] == "connected"


class TestRootEndpoint:
    """Integration tests for root endpoint."""

    def test_root_endpoint_returns_api_info(self, api_client):
        """Test that root endpoint returns API metadata."""
        # Act
        response = api_client.get("/")

        # Assert
        assert response.status_code == 200
        data = response.json()

        assert data["name"] == "NPS Trails API"
        assert data["version"] == "1.0.0"
        assert "endpoints" in data
        assert data["endpoints"]["parks"] == "/parks"
        assert data["endpoints"]["trails"] == "/trails"

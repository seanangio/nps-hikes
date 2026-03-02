"""
Integration tests for trail collector → database pipelines.

These tests verify that OSM and TNM trail collectors correctly write trail data
to the PostgreSQL/PostGIS database with proper schema compliance and spatial
data integrity.

Test Strategy:
- Use real external APIs (OSM Overpass, TNM) with minimal data
- Write to test database
- Verify PostGIS geometries and constraints
- Keep tests fast by using parks with few trails or test limits

Run with:
    pytest tests/integration/test_trail_collectors_db.py -v -m integration
"""

import os

import pytest
from sqlalchemy import text

from scripts.collectors.osm_hikes_collector import OSMHikesCollector
from scripts.collectors.tnm_hikes_collector import TNMHikesCollector
from scripts.database.db_writer import DatabaseWriter

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


class TestOSMCollectorDatabaseIntegration:
    """Integration tests for OSM trail collection and database storage."""

    def test_osm_collector_writes_trails_to_database(self, test_db_writer, tmp_path):
        """
        Test that OSM collector successfully writes trail data to database.

        This test verifies:
        1. Park boundaries are loaded from database (prerequisite)
        2. OSM trails are fetched via Overpass API
        3. Trails are written to osm_hikes table
        4. PostGIS geometries are valid
        5. Foreign key relationships are maintained

        Uses a small park to keep API calls and processing fast.
        May skip if park has no OSM trail data available.
        """
        # Arrange - Set up prerequisite park data
        api_key = os.getenv("NPS_API_KEY")
        if not api_key:
            pytest.skip("NPS_API_KEY not set - skipping integration test")

        from scripts.collectors.nps_collector import NPSDataCollector

        # Create park and boundary (prerequisite for trail collection)
        nps_collector = NPSDataCollector(api_key=api_key)
        csv_path = tmp_path / "test_parks.csv"
        csv_path.write_text("park_name,month,year\nAcadia,Oct,2024\n")

        parks_df = nps_collector.process_park_data(
            csv_path=str(csv_path), limit_for_testing=1
        )
        test_db_writer.write_parks(parks_df, mode="upsert")

        park_code = parks_df.iloc[0]["park_code"]
        boundaries_gdf = nps_collector.process_park_boundaries(
            park_codes=[park_code], limit_for_testing=1
        )

        if boundaries_gdf.empty:
            pytest.skip(f"No boundary data for {park_code} - skipping OSM test")

        test_db_writer.write_park_boundaries(boundaries_gdf, mode="upsert")

        # Act - Collect OSM trails
        output_gpkg = tmp_path / "osm_trails.gpkg"
        osm_collector = OSMHikesCollector(
            output_gpkg=str(output_gpkg),
            rate_limit=0.5,  # Minimal delay for testing
            parks=[park_code],
            test_limit=1,  # Process only 1 park
            log_level="INFO",
            write_db=True,
        )

        # Override engine and db_writer to use test database (not production)
        osm_collector.engine = test_db_writer.engine
        osm_collector.db_writer = test_db_writer
        # Refresh completed parks list from test database (not production)
        osm_collector.completed_parks = osm_collector.get_completed_parks()

        trails_gdf = osm_collector.collect_all_trails()

        # Assert - Verify trails in database
        if not trails_gdf.empty:
            with test_db_writer.engine.connect() as conn:
                # Check trail count
                result = conn.execute(
                    text("SELECT COUNT(*) FROM osm_hikes WHERE park_code = :park_code"),
                    {"park_code": park_code},
                )
                count = result.scalar()
                assert count > 0, f"Should have trails for {park_code} in database"

                # Get first trail
                result = conn.execute(
                    text(
                        """
                    SELECT osm_id, park_code, highway, length_miles,
                           ST_IsValid(geometry) as is_valid,
                           ST_GeometryType(geometry) as geom_type,
                           geometry_type
                    FROM osm_hikes
                    WHERE park_code = :park_code
                    LIMIT 1
                """
                    ),
                    {"park_code": park_code},
                )
                row = result.fetchone()

                # Verify data integrity
                assert row is not None, "Should retrieve trail data"
                assert row[1] == park_code, "park_code should match"
                assert row[2] is not None, "highway should not be NULL"
                assert row[3] > 0, "length_miles should be positive"
                assert row[4] is True, "Geometry should be valid PostGIS geometry"
                assert "LineString" in row[5], f"Expected LineString, got {row[5]}"

                # Verify foreign key relationship
                result = conn.execute(
                    text("SELECT park_code FROM parks WHERE park_code = :park_code"),
                    {"park_code": park_code},
                )
                assert result.fetchone() is not None, (
                    "Parent park should exist (FK constraint)"
                )

                # Verify spatial index exists
                result = conn.execute(
                    text(
                        """
                    SELECT indexname FROM pg_indexes
                    WHERE tablename = 'osm_hikes'
                    AND indexname = 'idx_osm_hikes_geometry'
                """
                    )
                )
                assert result.fetchone() is not None, (
                    "Spatial index should exist for geometries"
                )
        else:
            pytest.skip(f"No OSM trails found for {park_code} - skipping validation")


class TestTNMCollectorDatabaseIntegration:
    """Integration tests for TNM trail collection and database storage."""

    def test_tnm_collector_writes_trails_to_database(self, test_db_writer, tmp_path):
        """
        Test that TNM collector successfully writes trail data to database.

        This test verifies:
        1. Park boundaries are loaded from database (prerequisite)
        2. TNM trails are fetched via USGS TNM API
        3. Trails are written to tnm_hikes table
        4. PostGIS geometries are valid
        5. Schema compliance (columns, types, constraints)

        Uses a small park to keep API calls fast.
        May skip if park has no TNM trail data available.
        """
        # Arrange - Set up prerequisite park data
        api_key = os.getenv("NPS_API_KEY")
        if not api_key:
            pytest.skip("NPS_API_KEY not set - skipping integration test")

        from scripts.collectors.nps_collector import NPSDataCollector

        # Create park and boundary (prerequisite for trail collection)
        nps_collector = NPSDataCollector(api_key=api_key)
        csv_path = tmp_path / "test_parks.csv"
        csv_path.write_text("park_name,month,year\nAcadia,Oct,2024\n")

        parks_df = nps_collector.process_park_data(
            csv_path=str(csv_path), limit_for_testing=1
        )
        test_db_writer.write_parks(parks_df, mode="upsert")

        park_code = parks_df.iloc[0]["park_code"]
        boundaries_gdf = nps_collector.process_park_boundaries(
            park_codes=[park_code], limit_for_testing=1
        )

        if boundaries_gdf.empty:
            pytest.skip(f"No boundary data for {park_code} - skipping TNM test")

        test_db_writer.write_park_boundaries(boundaries_gdf, mode="upsert")

        # Act - Collect TNM trails
        output_gpkg = tmp_path / "tnm_trails.gpkg"
        tnm_collector = TNMHikesCollector(
            output_gpkg=str(output_gpkg),
            rate_limit=0.5,  # Minimal delay for testing
            parks=[park_code],
            test_limit=1,  # Process only 1 park
            log_level="INFO",
            write_db=True,
        )

        # Override engine and db_writer to use test database (not production)
        tnm_collector.engine = test_db_writer.engine
        tnm_collector.db_writer = test_db_writer
        # Refresh completed parks list from test database (not production)
        tnm_collector.completed_parks = tnm_collector.get_completed_parks()

        trails_gdf = tnm_collector.collect_all_trails()

        # Assert - Verify trails in database
        if not trails_gdf.empty:
            with test_db_writer.engine.connect() as conn:
                # Check trail count
                result = conn.execute(
                    text("SELECT COUNT(*) FROM tnm_hikes WHERE park_code = :park_code"),
                    {"park_code": park_code},
                )
                count = result.scalar()
                assert count > 0, f"Should have trails for {park_code} in database"

                # Get first trail
                result = conn.execute(
                    text(
                        """
                    SELECT permanent_identifier, park_code, name,
                           length_miles, ST_IsValid(geometry) as is_valid,
                           ST_GeometryType(geometry) as geom_type
                    FROM tnm_hikes
                    WHERE park_code = :park_code
                    LIMIT 1
                """
                    ),
                    {"park_code": park_code},
                )
                row = result.fetchone()

                # Verify data integrity
                assert row is not None, "Should retrieve trail data"
                assert row[0] is not None, "permanent_identifier should not be NULL"
                assert row[1] == park_code, "park_code should match"
                assert row[3] > 0, "length_miles should be positive"
                assert row[4] is True, "Geometry should be valid PostGIS geometry"
                assert "LineString" in row[5] or "MultiLineString" in row[5], (
                    f"Expected LineString or MultiLineString, got {row[5]}"
                )

                # Verify foreign key relationship
                result = conn.execute(
                    text("SELECT park_code FROM parks WHERE park_code = :park_code"),
                    {"park_code": park_code},
                )
                assert result.fetchone() is not None, (
                    "Parent park should exist (FK constraint)"
                )

                # Verify spatial index exists
                result = conn.execute(
                    text(
                        """
                    SELECT indexname FROM pg_indexes
                    WHERE tablename = 'tnm_hikes'
                    AND indexname = 'idx_tnm_hikes_geometry'
                """
                    )
                )
                assert result.fetchone() is not None, (
                    "Spatial index should exist for geometries"
                )
        else:
            pytest.skip(f"No TNM trails found for {park_code} - skipping validation")

    def test_tnm_trails_have_unique_identifiers(self, test_db_writer, tmp_path):
        """
        Test that TNM trails use permanent_identifier as primary key.

        This test verifies:
        1. Each trail has a permanent_identifier
        2. permanent_identifier is unique (PRIMARY KEY constraint)
        3. Cannot insert duplicate permanent_identifier
        """
        # This test uses direct database operations without API calls
        with (
            pytest.raises(Exception) as exc_info,
            test_db_writer.engine.begin() as conn,
        ):
            # Insert a test trail
            conn.execute(
                text(
                    """
                INSERT INTO parks (park_code, park_name, collection_status)
                VALUES ('test', 'Test Park', 'success')
            """
                )
            )
            conn.execute(
                text(
                    """
                INSERT INTO tnm_hikes
                    (permanent_identifier, park_code, name, length_miles, geometry, geometry_type)
                VALUES
                    ('test_id_123', 'test', 'Test Trail', 1.5,
                     ST_GeomFromText('LINESTRING(-120 45, -120.01 45.01)', 4326), 'LineString')
            """
                )
            )
            # Try to insert duplicate - should fail
            conn.execute(
                text(
                    """
                INSERT INTO tnm_hikes
                    (permanent_identifier, park_code, name, length_miles, geometry, geometry_type)
                VALUES
                    ('test_id_123', 'test', 'Duplicate Trail', 2.0,
                     ST_GeomFromText('LINESTRING(-120 45, -120.02 45.02)', 4326), 'LineString')
            """
                )
            )

        assert (
            "duplicate" in str(exc_info.value).lower()
            or "unique" in str(exc_info.value).lower()
        )

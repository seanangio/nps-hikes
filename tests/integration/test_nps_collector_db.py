"""
Integration tests for NPS collector → database pipeline.

These tests verify that the NPS collector correctly writes park data to the
PostgreSQL/PostGIS database with proper schema compliance and data integrity.

Test Strategy:
- Use real NPS API (with test-limit to minimize data)
- Write to test database
- Verify data persistence and schema compliance
- Focus on parks only (no trails/elevation) for speed

Run with:
    pytest tests/integration/test_nps_collector_db.py -v -m integration
"""

import os

import pytest
from sqlalchemy import text

from scripts.collectors.nps_collector import NPSDataCollector
from scripts.database.db_writer import DatabaseWriter

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


class TestNPSCollectorDatabaseIntegration:
    """Integration tests for NPS data collection and database storage."""

    def test_nps_collector_writes_park_metadata_to_database(
        self, test_db_writer, tmp_path
    ):
        """
        Test that NPS collector successfully writes park metadata to database.

        This test verifies the complete flow:
        1. Collect park data from NPS API (1 park only for speed)
        2. Write to test database using DatabaseWriter
        3. Verify data exists in database
        4. Validate schema compliance (columns, types, constraints)

        Uses a single park from a minimal test CSV.
        """
        # Arrange - Create collector with real API key
        api_key = os.getenv("NPS_API_KEY")
        if not api_key:
            pytest.skip("NPS_API_KEY not set - skipping integration test")

        collector = NPSDataCollector(api_key=api_key)

        # Create a minimal CSV with just one park
        csv_path = tmp_path / "test_parks.csv"
        csv_path.write_text("park_name,month,year\nAcadia,Oct,2024\n")

        # Act - Collect parks data (limited to 1 park for speed)
        parks_df = collector.process_park_data(
            csv_path=str(csv_path), limit_for_testing=1
        )

        # Verify we got data
        assert not parks_df.empty, "Collector should return at least 1 park"
        assert len(parks_df) >= 1, "Should collect at least 1 park"

        # Write to database
        test_db_writer.write_parks(parks_df, mode="upsert")

        # Assert - Verify data in database
        with test_db_writer.engine.connect() as conn:
            # Check that park was written
            result = conn.execute(text("SELECT COUNT(*) FROM parks"))
            count = result.scalar()
            assert count >= 1, "Should have at least 1 park in database"

            # Get the first park data
            result = conn.execute(
                text(
                    """
                SELECT park_code, park_name, full_name, designation,
                       states, latitude, longitude, collection_status
                FROM parks
                LIMIT 1
            """
                )
            )
            row = result.fetchone()

            # Verify required fields are populated
            assert row is not None, "Should retrieve park data"
            assert row[0] is not None, "park_code should not be NULL"
            assert len(row[0]) == 4, "park_code should be 4 characters"
            assert row[0].islower(), "park_code should be lowercase"
            assert row[1] is not None, "park_name should not be NULL"
            assert row[7] == "success", "collection_status should be 'success'"

            # Verify coordinate constraints
            latitude, longitude = row[5], row[6]
            if latitude is not None:
                assert -90 <= latitude <= 90, (
                    f"latitude {latitude} should be between -90 and 90"
                )
            if longitude is not None:
                assert -180 <= longitude <= 180, (
                    f"longitude {longitude} should be between -180 and 180"
                )

    def test_nps_collector_writes_park_boundaries_to_database(
        self, test_db_writer, tmp_path
    ):
        """
        Test that NPS collector successfully writes park boundaries to PostGIS.

        This test verifies:
        1. Park metadata is written first (dependency)
        2. Boundary geometries are collected and stored
        3. PostGIS geometry is valid
        4. Foreign key relationships are maintained

        Uses 1 park to keep test fast while validating spatial data handling.
        """
        # Arrange
        api_key = os.getenv("NPS_API_KEY")
        if not api_key:
            pytest.skip("NPS_API_KEY not set - skipping integration test")

        collector = NPSDataCollector(api_key=api_key)

        # Create a minimal CSV
        csv_path = tmp_path / "test_parks.csv"
        csv_path.write_text("park_name,month,year\nAcadia,Oct,2024\n")

        # Act - Collect parks and boundaries (1 park only)
        parks_df = collector.process_park_data(
            csv_path=str(csv_path), limit_for_testing=1
        )
        test_db_writer.write_parks(parks_df, mode="upsert")

        # Get park code for boundary collection
        park_code = parks_df.iloc[0]["park_code"]

        # Collect boundary for this park
        boundaries_gdf = collector.process_park_boundaries(
            park_codes=[park_code], limit_for_testing=1
        )

        # Only proceed if boundary data was collected
        if not boundaries_gdf.empty:
            test_db_writer.write_park_boundaries(boundaries_gdf, mode="upsert")

            # Assert - Verify boundary data
            with test_db_writer.engine.connect() as conn:
                result = conn.execute(
                    text(
                        """
                    SELECT park_code, boundary_source, geometry_type,
                           ST_IsValid(geometry) as is_valid,
                           ST_GeometryType(geometry) as geom_type,
                           collection_status
                    FROM park_boundaries
                    WHERE park_code = :park_code
                """
                    ),
                    {"park_code": park_code},
                )
                row = result.fetchone()

                assert row is not None, f"Boundary for {park_code} should exist"
                assert row[0] == park_code, "park_code should match"
                assert row[1] is not None, "boundary_source should be set"
                assert row[3] is True, "Geometry should be valid PostGIS geometry"
                assert "MultiPolygon" in row[4], (
                    f"Geometry type should be MultiPolygon, got {row[4]}"
                )
                assert row[5] == "success", "collection_status should be 'success'"

                # Verify foreign key relationship
                result = conn.execute(
                    text("SELECT park_code FROM parks WHERE park_code = :park_code"),
                    {"park_code": park_code},
                )
                assert result.fetchone() is not None, (
                    "Parent park should exist (FK constraint)"
                )
        else:
            # If no boundary was collected, verify error status
            pytest.skip(
                f"Park {park_code} has no boundary data available - skipping geometry validation"
            )

    def test_park_upsert_updates_existing_records(self, test_db_writer, tmp_path):
        """
        Test that upserting parks updates existing records instead of failing.

        This test verifies:
        1. Initial insert works
        2. Re-inserting same park updates the record
        3. No duplicate park_code violations occur
        """
        # Arrange
        api_key = os.getenv("NPS_API_KEY")
        if not api_key:
            pytest.skip("NPS_API_KEY not set - skipping integration test")

        collector = NPSDataCollector(api_key=api_key)

        # Create a minimal CSV
        csv_path = tmp_path / "test_parks.csv"
        csv_path.write_text("park_name,month,year\nAcadia,Oct,2024\n")

        # Act - Collect and write parks twice
        parks_df = collector.process_park_data(
            csv_path=str(csv_path), limit_for_testing=1
        )
        test_db_writer.write_parks(parks_df, mode="upsert")
        test_db_writer.write_parks(parks_df, mode="upsert")  # Second write

        # Assert - Should still have the same number of parks (no duplicates)
        with test_db_writer.engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM parks"))
            count = result.scalar()
            expected_count = len(parks_df)
            assert count == expected_count, (
                f"Upsert should not create duplicates, expected {expected_count}, got {count}"
            )

    def test_database_constraints_enforced(self, test_db):
        """
        Test that database constraints are properly enforced.

        Verifies:
        1. park_code PRIMARY KEY constraint
        2. Latitude/longitude CHECK constraints
        3. park_code format CHECK constraint (4 lowercase letters)
        """
        # Test invalid park_code (not 4 characters)
        with pytest.raises(Exception) as exc_info, test_db.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO parks (park_code, park_name, collection_status)
                    VALUES ('invalid', 'Invalid Park', 'success')
                """
                )
            )
        assert "park_code" in str(exc_info.value).lower()

        # Test invalid latitude (out of range)
        with pytest.raises(Exception) as exc_info, test_db.begin() as conn:
            conn.execute(
                text(
                    """
                INSERT INTO parks (park_code, park_name, latitude, collection_status)
                VALUES ('test', 'Test Park', 100.0, 'success')
            """
                )
            )
        assert "latitude" in str(exc_info.value).lower()

        # Test duplicate park_code (PRIMARY KEY violation)
        with pytest.raises(Exception) as exc_info, test_db.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO parks (park_code, park_name, collection_status)
                    VALUES ('test', 'Test Park 1', 'success')
                """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO parks (park_code, park_name, collection_status)
                    VALUES ('test', 'Test Park 2', 'success')
                """
                )
            )
        assert (
            "duplicate" in str(exc_info.value).lower()
            or "unique" in str(exc_info.value).lower()
        )

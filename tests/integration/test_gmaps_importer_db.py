"""
Integration tests for GMaps hiking locations importer → database pipeline.

These tests verify that the GMaps importer correctly parses KML files and writes
location data to the PostgreSQL database with proper schema compliance.

Test Strategy:
- Use real KML files from raw_data/gmaps/ directory
- Create minimal test KML files for controlled testing
- Write to test database
- Verify data integrity and foreign key constraints

Run with:
    pytest tests/integration/test_gmaps_importer_db.py -v -m integration
"""

import os
from pathlib import Path

import pytest
from sqlalchemy import text

from scripts.collectors.gmaps_hiking_importer import GMapsHikingImporter
from scripts.database.db_writer import DatabaseWriter

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


class TestGMapsImporterDatabaseIntegration:
    """Integration tests for GMaps hiking location import and database storage."""

    def test_gmaps_importer_writes_locations_to_database(
        self, test_db_writer, tmp_path
    ):
        """
        Test that GMaps importer successfully writes location data to database.

        This test verifies:
        1. KML files are parsed correctly
        2. Location data is validated
        3. Data is written to gmaps_hiking_locations table
        4. Foreign key constraints are enforced (park must exist)
        5. Coordinate validation works

        Uses a minimal test KML file for controlled testing.
        """
        # Arrange - Create prerequisite park
        api_key = os.getenv("NPS_API_KEY")
        if not api_key:
            pytest.skip("NPS_API_KEY not set - skipping integration test")

        from scripts.collectors.nps_collector import NPSDataCollector

        # Create a park first (GMaps importer validates against parks table)
        nps_collector = NPSDataCollector(api_key=api_key)
        csv_path = tmp_path / "test_parks.csv"
        csv_path.write_text("park_name,month,year\nZion,May,2023\n")

        parks_df = nps_collector.process_park_data(
            csv_path=str(csv_path), limit_for_testing=1
        )
        test_db_writer.write_parks(parks_df, mode="upsert")

        park_code = parks_df.iloc[0]["park_code"]

        # Create a minimal test KML file
        kml_dir = tmp_path / "test_gmaps"
        kml_dir.mkdir()
        kml_file = kml_dir / f"nps_points_{park_code}.kml"

        # Write a minimal valid KML with one location
        # KML structure: Document > Folder (park_code) > Placemark (location)
        kml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Test Hiking Locations</name>
    <Folder>
      <name>{park_code}</name>
      <Placemark>
        <name>Test Trail</name>
        <Point>
          <coordinates>-113.0265,37.2982,0</coordinates>
        </Point>
      </Placemark>
    </Folder>
  </Document>
</kml>"""

        kml_file.write_text(kml_content)

        # Act - Import GMaps data
        # Temporarily change working directory to use test KML files
        original_cwd = os.getcwd()
        try:
            # Create a config-like structure for the importer
            import sys

            sys.path.insert(0, str(tmp_path))

            # Import with write_db=True
            importer = GMapsHikingImporter(write_db=True)
            # Override the KML directory
            importer.kml_directory = str(kml_dir)
            # Override the database connection to use test database
            importer.engine = test_db_writer.engine
            importer.db_writer = test_db_writer

            # Import the data
            importer.import_gmaps_hiking_data(force_refresh=False)

            # Assert - Verify data in database
            with test_db_writer.engine.connect() as conn:
                # Check location count for this park
                result = conn.execute(
                    text(
                        "SELECT COUNT(*) FROM gmaps_hiking_locations WHERE park_code = :park_code"
                    ),
                    {"park_code": park_code},
                )
                count = result.scalar()
                assert count >= 1, (
                    f"Should have at least 1 location for {park_code} in database"
                )

                # Get first location
                result = conn.execute(
                    text(
                        """
                    SELECT id, park_code, location_name, latitude, longitude, created_at
                    FROM gmaps_hiking_locations
                    WHERE park_code = :park_code
                    LIMIT 1
                """
                    ),
                    {"park_code": park_code},
                )
                row = result.fetchone()

                # Verify data integrity
                assert row is not None, "Should retrieve location data"
                assert row[0] is not None, "id should not be NULL (auto-generated)"
                assert row[1] == park_code, "park_code should match"
                assert row[2] is not None, "location_name should not be NULL"
                assert row[3] is not None, "latitude should not be NULL"
                assert row[4] is not None, "longitude should not be NULL"
                assert row[5] is not None, "created_at should not be NULL"

                # Verify coordinate constraints
                latitude, longitude = row[3], row[4]
                assert -90 <= latitude <= 90, (
                    f"latitude {latitude} should be between -90 and 90"
                )
                assert -180 <= longitude <= 180, (
                    f"longitude {longitude} should be between -180 and 180"
                )

                # Verify foreign key relationship
                result = conn.execute(
                    text("SELECT park_code FROM parks WHERE park_code = :park_code"),
                    {"park_code": park_code},
                )
                assert result.fetchone() is not None, (
                    "Parent park should exist (FK constraint)"
                )

        finally:
            os.chdir(original_cwd)
            if str(tmp_path) in sys.path:
                sys.path.remove(str(tmp_path))

    def test_gmaps_importer_validates_park_codes(self, test_db_writer, tmp_path):
        """
        Test that GMaps importer validates park codes against parks table.

        This test verifies:
        1. Only locations for valid parks (in parks table) are imported
        2. Locations for invalid/unknown parks are skipped or cause errors
        """
        # Arrange - Create a KML file with an invalid park code
        kml_dir = tmp_path / "test_gmaps"
        kml_dir.mkdir()
        kml_file = kml_dir / "nps_points_fake.kml"

        kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Invalid Park Test</name>
    <Placemark>
      <name>Fake Trail</name>
      <Point>
        <coordinates>-120.0,40.0,0</coordinates>
      </Point>
    </Placemark>
  </Document>
</kml>"""

        kml_file.write_text(kml_content)

        # Act - Try to import with invalid park code
        original_cwd = os.getcwd()
        try:
            importer = GMapsHikingImporter(write_db=True)
            importer.kml_directory = str(kml_dir)
            # Override the database connection to use test database
            importer.engine = test_db_writer.engine
            importer.db_writer = test_db_writer

            # Import should handle invalid park gracefully (skip or log error)
            importer.import_gmaps_hiking_data(force_refresh=False)

            # Assert - Verify no data was written for invalid park
            with test_db_writer.engine.connect() as conn:
                result = conn.execute(
                    text(
                        "SELECT COUNT(*) FROM gmaps_hiking_locations WHERE park_code = 'fake'"
                    )
                )
                count = result.scalar()
                assert count == 0, "Should not import locations for invalid park codes"

        finally:
            os.chdir(original_cwd)

    def test_gmaps_locations_have_auto_increment_ids(self, test_db_writer):
        """
        Test that gmaps_hiking_locations uses auto-incrementing primary key.

        This test verifies:
        1. ID is auto-generated (not manually specified)
        2. IDs are unique
        3. IDs increment sequentially
        """
        # Arrange - Create a test park
        with test_db_writer.engine.begin() as conn:
            conn.execute(
                text(
                    """
                INSERT INTO parks (park_code, park_name, collection_status)
                VALUES ('test', 'Test Park', 'success')
            """
                )
            )

            # Act - Insert locations without specifying ID
            conn.execute(
                text(
                    """
                INSERT INTO gmaps_hiking_locations (park_code, location_name, latitude, longitude)
                VALUES ('test', 'Location 1', 40.0, -120.0)
            """
                )
            )
            conn.execute(
                text(
                    """
                INSERT INTO gmaps_hiking_locations (park_code, location_name, latitude, longitude)
                VALUES ('test', 'Location 2', 40.1, -120.1)
            """
                )
            )

            # Assert - Check that IDs were auto-generated
            result = conn.execute(
                text(
                    """
                SELECT id FROM gmaps_hiking_locations
                WHERE park_code = 'test'
                ORDER BY id
            """
                )
            )
            ids = [row[0] for row in result.fetchall()]

            assert len(ids) == 2, "Should have 2 locations"
            assert ids[0] is not None, "First ID should be auto-generated"
            assert ids[1] is not None, "Second ID should be auto-generated"
            assert ids[0] != ids[1], "IDs should be unique"
            assert ids[1] > ids[0], "IDs should increment"

    def test_gmaps_force_refresh_replaces_existing_data(self, test_db_writer, tmp_path):
        """
        Test that force_refresh deletes and replaces existing park locations.

        This test verifies:
        1. Initial import creates locations
        2. force_refresh=True deletes existing locations for that park
        3. New import replaces old data
        """
        # Arrange - Create park and initial location
        api_key = os.getenv("NPS_API_KEY")
        if not api_key:
            pytest.skip("NPS_API_KEY not set - skipping integration test")

        from scripts.collectors.nps_collector import NPSDataCollector

        nps_collector = NPSDataCollector(api_key=api_key)
        csv_path = tmp_path / "test_parks.csv"
        csv_path.write_text("park_name,month,year\nAcadia,Oct,2024\n")

        parks_df = nps_collector.process_park_data(
            csv_path=str(csv_path), limit_for_testing=1
        )
        test_db_writer.write_parks(parks_df, mode="upsert")
        park_code = parks_df.iloc[0]["park_code"]

        # Insert initial location manually
        with test_db_writer.engine.begin() as conn:
            conn.execute(
                text(
                    """
                INSERT INTO gmaps_hiking_locations (park_code, location_name, latitude, longitude)
                VALUES (:park_code, 'Old Location', 40.0, -120.0)
            """
                ),
                {"park_code": park_code},
            )

        # Act - Import with force_refresh (should delete and replace)
        kml_dir = tmp_path / "test_gmaps"
        kml_dir.mkdir()
        kml_file = kml_dir / f"nps_points_{park_code}.kml"

        kml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>New Locations</name>
    <Folder>
      <name>{park_code}</name>
      <Placemark>
        <name>New Location</name>
        <Point>
          <coordinates>-113.0265,37.2982,0</coordinates>
        </Point>
      </Placemark>
    </Folder>
  </Document>
</kml>"""

        kml_file.write_text(kml_content)

        original_cwd = os.getcwd()
        try:
            import sys

            sys.path.insert(0, str(tmp_path))

            importer = GMapsHikingImporter(write_db=True)
            importer.kml_directory = str(kml_dir)
            # Override the database connection to use test database
            importer.engine = test_db_writer.engine
            importer.db_writer = test_db_writer
            importer.import_gmaps_hiking_data(force_refresh=True)

            # Assert - Verify old location is gone, new location exists
            with test_db_writer.engine.connect() as conn:
                result = conn.execute(
                    text(
                        """
                    SELECT location_name FROM gmaps_hiking_locations
                    WHERE park_code = :park_code
                """
                    ),
                    {"park_code": park_code},
                )
                locations = [row[0] for row in result.fetchall()]

                assert "Old Location" not in locations, "Old location should be deleted"
                assert "New Location" in locations, "New location should be imported"

        finally:
            os.chdir(original_cwd)
            if str(tmp_path) in sys.path:
                sys.path.remove(str(tmp_path))

#!/usr/bin/env python3
"""
Unit tests for Google Maps hiking locations importer.
"""

import pytest
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
from datetime import datetime

# Add project root to path for imports
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "../.."))

from scripts.collectors.gmaps_hiking_importer import GMapsHikingImporter


class TestGMapsHikingImporter:
    """Test cases for GMapsHikingImporter class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.importer = GMapsHikingImporter(write_db=False)

        # Sample KML data for testing
        self.sample_kml = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Folder>
      <name>pinn</name>
      <Placemark>
        <name>Juniper Canyon Trail</name>
        <Point>
          <coordinates>-121.2047223,36.4871085,0</coordinates>
        </Point>
      </Placemark>
      <Placemark>
        <name>Balconies Cave Trail</name>
        <Point>
          <coordinates>-121.2011774,36.5002002,0</coordinates>
        </Point>
      </Placemark>
    </Folder>
    <Folder>
      <name>seki</name>
      <Placemark>
        <name>The Congress Trail</name>
        <Point>
          <coordinates>-118.750251,36.5809946,0</coordinates>
        </Point>
      </Placemark>
    </Folder>
  </Document>
</kml>"""

    def test_parse_kml_file_valid(self):
        """Test parsing valid KML file."""
        # Create temporary directory with KML file
        temp_dir = tempfile.mkdtemp()
        temp_kml_path = os.path.join(temp_dir, "test_parks.kml")

        with open(temp_kml_path, "w") as f:
            f.write(self.sample_kml)

        try:
            # Patch the directory path
            self.importer.kml_directory = temp_dir

            # Parse the KML directory
            result = self.importer.parse_kml_directory()

            # Verify results
            assert len(result) == 2
            assert "pinn" in result
            assert "seki" in result

            # Check pinn locations
            pinn_locations = result["pinn"]
            assert len(pinn_locations) == 2
            assert pinn_locations[0]["location_name"] == "Juniper Canyon Trail"
            assert pinn_locations[0]["latitude"] == 36.4871085
            assert pinn_locations[0]["longitude"] == -121.2047223

            # Check seki locations
            seki_locations = result["seki"]
            assert len(seki_locations) == 1
            assert seki_locations[0]["location_name"] == "The Congress Trail"

        finally:
            # Clean up
            os.unlink(temp_kml_path)
            os.rmdir(temp_dir)

    def test_parse_kml_file_missing(self):
        """Test parsing non-existent KML directory."""
        self.importer.kml_directory = "/nonexistent/directory"

        # Should return empty dict when directory doesn't exist
        result = self.importer.parse_kml_directory()
        assert result == {}

    def test_validate_location_valid_coords(self):
        """Test validation of location with valid coordinates."""
        # Mock the NPS collector for coordinate validation
        mock_nps_collector = Mock()
        mock_nps_collector._validate_coordinates.return_value = (
            36.4871085,
            -121.2047223,
        )
        self.importer.nps_collector = mock_nps_collector

        location = {
            "park_code": "pinn",
            "location_name": "Test Trail",
            "latitude": 36.4871085,
            "longitude": -121.2047223,
        }

        is_valid, lat, lon = self.importer.validate_location(location)

        assert is_valid is True
        assert lat == 36.4871085
        assert lon == -121.2047223

    def test_validate_location_invalid_coords(self):
        """Test validation of location with invalid coordinates."""
        # Mock the NPS collector to return None for invalid coords
        mock_nps_collector = Mock()
        mock_nps_collector._validate_coordinates.return_value = (None, None)
        self.importer.nps_collector = mock_nps_collector

        location = {
            "park_code": "pinn",
            "location_name": "Test Trail",
            "latitude": 999.0,  # Invalid latitude
            "longitude": -121.2047223,
        }

        is_valid, lat, lon = self.importer.validate_location(location)

        assert is_valid is True  # Still valid, just no coords
        assert lat is None
        assert lon is None

    def test_validate_location_no_coords(self):
        """Test validation of location without coordinates."""
        location = {
            "park_code": "pinn",
            "location_name": "Test Trail",
            "latitude": None,
            "longitude": None,
        }

        is_valid, lat, lon = self.importer.validate_location(location)

        assert is_valid is True
        assert lat is None
        assert lon is None

    def test_create_csv_artifact(self):
        """Test CSV artifact creation."""
        # Sample locations
        locations = [
            {
                "park_code": "pinn",
                "location_name": "Juniper Canyon Trail",
                "latitude": 36.4871085,
                "longitude": -121.2047223,
            },
            {
                "park_code": "seki",
                "location_name": "The Congress Trail",
                "latitude": 36.5809946,
                "longitude": -118.750251,
            },
        ]

        # Create CSV artifact
        self.importer.create_csv_artifact(locations)

        # Check if file was created
        output_path = "artifacts/gmaps_hiking_locations.csv"
        assert os.path.exists(output_path)

        # Verify CSV content
        df = pd.read_csv(output_path)
        assert len(df) == 2
        assert list(df.columns) == [
            "id",
            "park_code",
            "location_name",
            "latitude",
            "longitude",
            "created_at",
        ]
        assert df.iloc[0]["park_code"] == "pinn"
        assert df.iloc[1]["park_code"] == "seki"

        # Clean up
        os.unlink(output_path)

    def test_import_park_locations_csv_mode(self):
        """Test importing park locations in CSV mode."""
        locations = [
            {
                "park_code": "pinn",
                "location_name": "Juniper Canyon Trail",
                "latitude": 36.4871085,
                "longitude": -121.2047223,
            }
        ]

        # Mock coordinate validation
        mock_nps_collector = Mock()
        mock_nps_collector._validate_coordinates.return_value = (
            36.4871085,
            -121.2047223,
        )
        self.importer.nps_collector = mock_nps_collector

        # Import locations
        result_df = self.importer.import_park_locations("pinn", locations)

        # Verify result
        assert result_df is not None
        assert len(result_df) == 1
        assert result_df.iloc[0]["location_name"] == "Juniper Canyon Trail"

    def test_import_park_locations_database_mode(self):
        """Test importing park locations in database mode."""
        # Switch to database mode
        self.importer.write_db = True

        # Mock database writer
        mock_db_writer = Mock()
        mock_db_writer.park_exists_in_gmaps_table.return_value = False
        mock_db_writer.write_gmaps_hiking_locations = Mock()
        self.importer.db_writer = mock_db_writer

        # Mock engine for park validation
        mock_engine = Mock()
        self.importer.engine = mock_engine

        # Mock park validation to return True (park exists)
        with patch.object(
            self.importer, "_park_exists_in_parks_table", return_value=True
        ):
            locations = [
                {
                    "park_code": "pinn",
                    "location_name": "Juniper Canyon Trail",
                    "latitude": 36.4871085,
                    "longitude": -121.2047223,
                }
            ]

            # Import locations
            self.importer.import_park_locations("pinn", locations)

            # Verify database writer was called
            mock_db_writer.write_gmaps_hiking_locations.assert_called_once()

    def test_import_park_locations_skip_existing(self):
        """Test skipping existing parks."""
        # Switch to database mode
        self.importer.write_db = True

        # Mock database writer to return existing park
        mock_db_writer = Mock()
        mock_db_writer.park_exists_in_gmaps_table.return_value = True
        self.importer.db_writer = mock_db_writer

        locations = [
            {
                "park_code": "pinn",
                "location_name": "Juniper Canyon Trail",
                "latitude": 36.4871085,
                "longitude": -121.2047223,
            }
        ]

        # Import locations
        self.importer.import_park_locations("pinn", locations)

        # Verify park was skipped
        assert self.importer.stats["parks_skipped"] == 1

        # Verify database writer was not called
        mock_db_writer.write_gmaps_hiking_locations.assert_not_called()

    def test_import_park_locations_force_refresh(self):
        """Test force refresh behavior."""
        # Switch to database mode
        self.importer.write_db = True

        # Mock database writer
        mock_db_writer = Mock()
        mock_db_writer.park_exists_in_gmaps_table.return_value = True
        mock_db_writer.delete_gmaps_park_records = Mock()
        mock_db_writer.write_gmaps_hiking_locations = Mock()
        self.importer.db_writer = mock_db_writer

        # Mock engine for park validation
        mock_engine = Mock()
        self.importer.engine = mock_engine

        # Mock park validation to return True (park exists)
        with patch.object(
            self.importer, "_park_exists_in_parks_table", return_value=True
        ):
            locations = [
                {
                    "park_code": "pinn",
                    "location_name": "Juniper Canyon Trail",
                    "latitude": 36.4871085,
                    "longitude": -121.2047223,
                }
            ]

            # Import locations with force refresh
            self.importer.import_park_locations("pinn", locations, force_refresh=True)

            # Verify existing records were deleted
            mock_db_writer.delete_gmaps_park_records.assert_called_once_with("pinn")

            # Verify new data was written
            mock_db_writer.write_gmaps_hiking_locations.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])

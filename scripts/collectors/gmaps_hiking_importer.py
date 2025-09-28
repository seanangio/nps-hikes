#!/usr/bin/env python3
"""
Google Maps Hiking Locations Importer

This script imports hiking location data from Google Maps KML files into the database.
It automatically discovers and processes all KML files in the configured directory.
It supports both CSV output (default) and database insertion (with --write-db flag).

Usage:
    # Parse all KML files in raw_data/gmaps/ and create CSV artifact (default)
    python gmaps_hiking_importer.py

    # Parse all KML files and write to database
    python gmaps_hiking_importer.py --write-db

    # Force refresh (drop existing records and re-import)
    python gmaps_hiking_importer.py --write-db --force-refresh
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import xml.etree.ElementTree as ET
import pandas as pd

# Add project root to path for imports
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from config.settings import config
from scripts.database.db_writer import DatabaseWriter, get_postgres_engine
from sqlalchemy import text

# Configure logging using centralized utility
from utils.logging import setup_logging
logger = setup_logging(
    log_level=config.LOG_LEVEL,
    log_file=config.GMAPS_LOG_FILE,
    logger_name="gmaps_importer"
)


class GMapsHikingImporter:
    """Import Google Maps hiking locations from KML files."""

    def __init__(self, write_db: bool = False):
        """
        Initialize the importer.

        Args:
            write_db (bool): Whether to write to database or just create CSV
        """
        self.write_db = write_db
        self.kml_directory = config.GMAPS_INPUT_DIRECTORY

        if self.write_db:
            self.engine = get_postgres_engine()
            self.db_writer = DatabaseWriter(self.engine, logger)

        # Statistics for summary report
        self.stats = {
            "total_parks": 0,
            "total_valid_parks": 0,
            "total_locations": 0,
            "parks_skipped": 0,
            "locations_with_coords": 0,
            "locations_missing_coords": 0,
            "failed_locations": 0,
            "processing_time": 0,
            "missing_park_codes": [],
        }

    def _discover_kml_files(self) -> List[str]:
        """
        Discover all KML files in the configured directory.

        Returns:
            List of KML file paths
        """
        if not os.path.exists(self.kml_directory):
            logger.warning(f"KML directory not found: {self.kml_directory}")
            return []

        kml_files = []
        for filename in sorted(os.listdir(self.kml_directory)):
            if filename.lower().endswith(".kml"):
                kml_files.append(os.path.join(self.kml_directory, filename))

        logger.info(f"Found {len(kml_files)} KML files in {self.kml_directory}")
        for kml_file in kml_files:
            logger.info(f"  - {os.path.basename(kml_file)}")

        return kml_files

    def parse_kml_directory(self) -> Dict[str, List[Dict]]:
        """
        Parse all KML files in the configured directory and extract hiking locations.

        Returns:
            Dict mapping park_code to list of location dictionaries
        """
        kml_files = self._discover_kml_files()

        if not kml_files:
            logger.warning("No KML files found to process")
            return {}

        all_parks_data = {}

        for kml_file_path in kml_files:
            logger.info(f"Processing KML file: {os.path.basename(kml_file_path)}")

            try:
                tree = ET.parse(kml_file_path)
                root = tree.getroot()

                # Remove namespace for easier parsing
                namespace = {"kml": "http://www.opengis.net/kml/2.2"}

                # Find all folders (park layers)
                folders = root.findall(".//kml:Folder", namespace)
                logger.info(
                    f"Found {len(folders)} park layers in {os.path.basename(kml_file_path)}"
                )

                for folder in folders:
                    folder_name = folder.find("kml:name", namespace)
                    if folder_name is None or not folder_name.text:
                        logger.warning("Found folder without name, skipping")
                        continue

                    park_code = folder_name.text.strip()
                    logger.info(f"Processing park: {park_code}")

                    # Find all placemarks (locations) in this park
                    placemarks = folder.findall(".//kml:Placemark", namespace)
                    locations = []

                    for placemark in placemarks:
                        location_name = placemark.find("kml:name", namespace)
                        if location_name is None or not location_name.text:
                            logger.warning(
                                f"Found placemark without name in {park_code}, skipping"
                            )
                            continue

                        location_name = location_name.text.strip()

                        # Extract coordinates
                        coords_elem = placemark.find(".//kml:coordinates", namespace)
                        lat, lon = None, None

                        if coords_elem is not None and coords_elem.text:
                            try:
                                coords_text = coords_elem.text.strip()
                                # Parse coordinates: "longitude,latitude,altitude"
                                lon_str, lat_str, alt_str = coords_text.split(",")
                                lat = float(lat_str)
                                lon = float(lon_str)
                            except (ValueError, IndexError) as e:
                                logger.warning(
                                    f"Could not parse coordinates for {location_name}: {e}"
                                )

                        locations.append(
                            {
                                "park_code": park_code,
                                "location_name": location_name,
                                "latitude": lat,
                                "longitude": lon,
                            }
                        )

                    # Merge with existing data for this park (if park appears in multiple files)
                    if park_code in all_parks_data:
                        logger.info(
                            f"Park {park_code} found in multiple files, merging locations"
                        )
                        all_parks_data[park_code].extend(locations)
                    else:
                        all_parks_data[park_code] = locations

                    logger.info(
                        f"Found {len(locations)} locations for park {park_code} in {os.path.basename(kml_file_path)}"
                    )

            except Exception as e:
                logger.error(
                    f"Failed to parse KML file {os.path.basename(kml_file_path)}: {e}"
                )
                continue

        # Remove duplicates based on park_code + location_name
        all_parks_data = self._remove_duplicates(all_parks_data)

        # Log final summary
        total_parks = len(all_parks_data)
        total_locations = sum(len(locations) for locations in all_parks_data.values())
        logger.info(f"Successfully parsed {len(kml_files)} KML files")
        logger.info(f"Total parks found: {total_parks}")
        logger.info(f"Total locations found: {total_locations}")

        return all_parks_data

    def _remove_duplicates(
        self, parks_data: Dict[str, List[Dict]]
    ) -> Dict[str, List[Dict]]:
        """
        Remove duplicate locations based on park_code + location_name.

        Args:
            parks_data: Dict mapping park_code to list of location dictionaries

        Returns:
            Dict with duplicates removed
        """
        deduplicated_data = {}

        for park_code, locations in parks_data.items():
            seen = set()
            unique_locations = []

            for location in locations:
                # Create unique key based on park_code + location_name
                key = (location["park_code"], location["location_name"])

                if key not in seen:
                    seen.add(key)
                    unique_locations.append(location)
                else:
                    logger.debug(
                        f"Removed duplicate: {location['park_code']} - {location['location_name']}"
                    )

            deduplicated_data[park_code] = unique_locations

            if len(unique_locations) < len(locations):
                logger.info(
                    f"Removed {len(locations) - len(unique_locations)} duplicates from park {park_code}"
                )

        return deduplicated_data

    def validate_location(
        self, location: Dict
    ) -> Tuple[bool, Optional[float], Optional[float]]:
        """
        Validate a location's data.

        Args:
            location: Location dictionary with park_code, location_name, lat, lon

        Returns:
            Tuple of (is_valid, validated_lat, validated_lon)
        """
        park_code = location["park_code"]
        location_name = location["location_name"]
        lat = location["latitude"]
        lon = location["longitude"]

        # Check if park_code exists in parks table
        if self.write_db and not self._park_exists_in_parks_table(park_code):
            logger.warning(
                f"Unknown park_code: {park_code}, skipping location: {location_name}"
            )
            return False, None, None

        # Validate coordinates if present
        if lat is not None and lon is not None:
            # Use simple coordinate validation
            validated_lat, validated_lon = self._validate_coordinates(
                lat, lon, f"{park_code}:{location_name}"
            )

            if validated_lat is None or validated_lon is None:
                logger.warning(
                    f"Invalid coordinates for {location_name}: ({lat}, {lon}), storing without coords"
                )
                return True, None, None

            return True, validated_lat, validated_lon

        # No coordinates provided
        logger.info(
            f"No coordinates provided for {location_name}, storing without coords"
        )
        return True, None, None

    def _validate_coordinates(
        self, lat: float, lon: float, context: str
    ) -> tuple[Optional[float], Optional[float]]:
        """
        Simple coordinate validation.

        Args:
            lat: Latitude value
            lon: Longitude value
            context: Context string for logging

        Returns:
            Tuple of (validated_lat, validated_lon) or (None, None) if invalid
        """
        try:
            # Validate geographic ranges
            if not (-90 <= lat <= 90):
                logger.warning(
                    f"Invalid latitude {lat} for {context} (must be between -90 and 90)"
                )
                return None, None

            if not (-180 <= lon <= 180):
                logger.warning(
                    f"Invalid longitude {lon} for {context} (must be between -180 and 180)"
                )
                return None, None

            logger.debug(f"Valid coordinates for {context}: ({lat}, {lon})")
            return lat, lon

        except (ValueError, TypeError) as e:
            logger.warning(f"Could not parse coordinates for {context}: {str(e)}")
            return None, None

    def _get_all_valid_park_codes(self) -> set:
        """Get all valid park codes from the parks table."""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT park_code FROM parks"))
                park_codes = {row.park_code for row in result}
                return park_codes
        except Exception as e:
            logger.error(f"Failed to get valid park codes: {e}")
            return set()

    def _park_exists_in_parks_table(self, park_code: str) -> bool:
        """Check if park_code exists in the parks table."""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text("SELECT COUNT(*) FROM parks WHERE park_code = :park_code"),
                    {"park_code": park_code},
                )
                count = result.scalar()
                return count > 0
        except Exception as e:
            logger.error(
                f"Failed to check if park {park_code} exists in parks table: {e}"
            )
            return False

    def import_park_locations(
        self, park_code: str, locations: List[Dict], force_refresh: bool = False
    ) -> None:
        """
        Import locations for a specific park.

        Args:
            park_code: Park code
            locations: List of location dictionaries
            force_refresh: Whether to drop existing records before import
        """
        if self.write_db:
            # Check if park already exists
            if not force_refresh and self.db_writer.park_exists_in_gmaps_table(
                park_code
            ):
                logger.info(f"Park {park_code} already exists, skipping...")
                self.stats["parks_skipped"] += 1
                return

            # If force_refresh, delete existing records
            if force_refresh and self.db_writer.park_exists_in_gmaps_table(park_code):
                logger.info(
                    f"Force refresh: deleting existing records for park {park_code}"
                )
                self.db_writer.delete_gmaps_park_records(park_code)

        # Process each location
        valid_locations = []

        for location in locations:
            try:
                is_valid, validated_lat, validated_lon = self.validate_location(
                    location
                )

                if not is_valid:
                    self.stats["failed_locations"] += 1
                    continue

                # Update location with validated coordinates
                location["latitude"] = validated_lat
                location["longitude"] = validated_lon

                # Track statistics
                if validated_lat is not None and validated_lon is not None:
                    self.stats["locations_with_coords"] += 1
                else:
                    self.stats["locations_missing_coords"] += 1

                valid_locations.append(location)

            except Exception as e:
                logger.error(
                    f"Failed to process location {location.get('location_name', 'Unknown')}: {e}"
                )
                self.stats["failed_locations"] += 1

        if valid_locations:
            # Create DataFrame
            df = pd.DataFrame(valid_locations)

            if self.write_db:
                # Write to database
                self.db_writer.write_gmaps_hiking_locations(df, mode="append")
                logger.info(
                    f"Imported {len(valid_locations)} locations for park {park_code}"
                )
            else:
                # Return for CSV creation
                return df

        self.stats["total_locations"] += len(valid_locations)

    def create_csv_artifact(self, all_locations: List[Dict]) -> None:
        """Create CSV artifact from all locations."""
        if not all_locations:
            logger.warning("No locations to write to CSV")
            return

        # Create DataFrame with all required columns
        df = pd.DataFrame(all_locations)

        # Add id and created_at columns to match DB schema
        df["id"] = range(1, len(df) + 1)
        df["created_at"] = datetime.now()

        # Reorder columns to match DB schema
        df = df[
            ["id", "park_code", "location_name", "latitude", "longitude", "created_at"]
        ]

        # Save to CSV
        output_path = "artifacts/gmaps_hiking_locations.csv"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        df.to_csv(output_path, index=False)

        logger.info(f"Created CSV artifact: {output_path}")
        logger.info(f"Total locations written: {len(df)}")

    def import_gmaps_hiking_data(self, force_refresh: bool = False) -> None:
        """
        Main import workflow.

        Args:
            force_refresh: Whether to force refresh existing data
        """
        start_time = datetime.now()
        logger.info("Starting Google Maps hiking locations import")

        try:
            # Parse KML directory
            parks_data = self.parse_kml_directory()
            self.stats["total_parks"] = len(parks_data)

            # Get valid park codes and calculate missing ones
            if self.write_db:
                valid_park_codes = self._get_all_valid_park_codes()
                self.stats["total_valid_parks"] = len(valid_park_codes)

                # Find missing park codes
                kml_park_codes = set(parks_data.keys())
                missing_park_codes = valid_park_codes - kml_park_codes
                self.stats["missing_park_codes"] = sorted(list(missing_park_codes))

            if not self.write_db:
                # CSV mode: collect all locations
                all_locations = []

                for park_code, locations in parks_data.items():
                    logger.info(f"Processing park: {park_code}")

                    for location in locations:
                        is_valid, validated_lat, validated_lon = self.validate_location(
                            location
                        )

                        if is_valid:
                            location["latitude"] = validated_lat
                            location["longitude"] = validated_lon

                            if validated_lat is not None and validated_lon is not None:
                                self.stats["locations_with_coords"] += 1
                            else:
                                self.stats["locations_missing_coords"] += 1

                            all_locations.append(location)
                        else:
                            self.stats["failed_locations"] += 1

                    self.stats["total_locations"] += len(locations)

                # Create CSV artifact
                self.create_csv_artifact(all_locations)

            else:
                # Database mode: import park by park
                for park_code, locations in parks_data.items():
                    self.import_park_locations(park_code, locations, force_refresh)

            # Calculate processing time
            self.stats["processing_time"] = (
                datetime.now() - start_time
            ).total_seconds()

            # Print summary
            self._print_summary()

        except Exception as e:
            logger.error(f"Import failed: {e}")
            raise

    def _print_summary(self) -> None:
        """Print import summary."""
        logger.info("=" * 50)
        logger.info("IMPORT SUMMARY")
        logger.info("=" * 50)
        logger.info(f"Total parks processed: {self.stats['total_parks']}")

        if self.write_db and self.stats["total_valid_parks"] > 0:
            logger.info(
                f"Total valid park codes in database: {self.stats['total_valid_parks']}"
            )
            if self.stats["missing_park_codes"]:
                logger.info(
                    f"Missing parks from KML: {', '.join(self.stats['missing_park_codes'])}"
                )
            else:
                logger.info("All valid park codes covered in KML")

        logger.info(f"Total locations processed: {self.stats['total_locations']}")
        logger.info(f"Parks skipped (already exist): {self.stats['parks_skipped']}")
        logger.info(
            f"Locations with coordinates: {self.stats['locations_with_coords']}"
        )
        logger.info(
            f"Locations missing coordinates: {self.stats['locations_missing_coords']}"
        )
        logger.info(f"Failed locations: {self.stats['failed_locations']}")
        logger.info(f"Processing time: {self.stats['processing_time']:.2f} seconds")

        if self.write_db:
            logger.info("Mode: Database import")
        else:
            logger.info("Mode: CSV artifact creation")

        logger.info("=" * 50)


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Import Google Maps hiking locations from KML files in configured directory"
    )
    parser.add_argument(
        "--write-db",
        action="store_true",
        help="Write data to database instead of creating CSV artifact",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Force refresh existing data (drop and re-import)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Set logging level",
    )

    args = parser.parse_args()

    # Set log level
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    try:
        # Initialize importer
        importer = GMapsHikingImporter(write_db=args.write_db)

        # Run import
        importer.import_gmaps_hiking_data(force_refresh=args.force_refresh)

        logger.info("Import completed successfully")

    except Exception as e:
        logger.error(f"Import failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

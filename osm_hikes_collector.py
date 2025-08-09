"""
OpenStreetMap Hiking Trails Collector for National Parks

This module provides a comprehensive solution for collecting hiking trail data from
OpenStreetMap (OSM) within National Park boundaries. It queries OSM's Overpass API
to download trail geometries, processes and validates the data, and stores results
in both file and database formats.

Key Features:
- Automated trail discovery using OSM's rich trail tagging system
- Spatial filtering within precise park boundary polygons
- Data quality validation and standardization
- Resumable collection runs for large datasets
- Rate limiting to respect OSM server policies
- Comprehensive logging and progress tracking
- Dual output: GeoPackage files and PostgreSQL/PostGIS database

Data Processing Pipeline:
1. Load park boundaries from database
2. Query OSM Overpass API for trail features within each park
3. Filter for linear geometries (LineString/MultiLineString)
4. Filter for named trails to focus on established hiking routes
5. Calculate accurate trail lengths using projected coordinate systems
6. Validate data quality and remove invalid/unrealistic records
7. Add metadata (park codes, timestamps, source attribution)
8. Write to both GeoPackage and database with proper spatial indexing
"""

# Standard library imports
import argparse
import os
from datetime import datetime, timezone
from typing import List, Optional, Set, Union
import logging

# Third-party imports
import geopandas as gpd
import osmnx as ox
import pandas as pd
from shapely.geometry import Polygon, MultiPolygon
from sqlalchemy import Engine
from dotenv import load_dotenv

# Load .env before local imports that need env vars
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# Local application imports
from config.settings import config
from db_writer import get_postgres_engine, DatabaseWriter

# Import centralized logging utility
from utils.logging import setup_osm_collector_logging


class OSMHikesCollector:
    """
    A class for collecting hiking trail data from OpenStreetMap within National Park boundaries.

    This class encapsulates functionality to query OpenStreetMap's Overpass API for hiking
    trails within park boundary polygons, process the geometric and attribute data,
    and save results to both file and database formats.
    """

    def __init__(
        self,
        output_gpkg: str,
        rate_limit: float,
        parks: Optional[List[str]],
        test_limit: Optional[int],
        log_level: str,
        write_db: bool,
    ) -> None:
        """
        Initialize the OSM hikes collector with configuration parameters.

        This constructor sets up logging, database connections, and tracks completion state
        for resumable collection runs. The collector can process all parks or be limited
        to specific parks for testing purposes.

        Args:
            output_gpkg (str): Path to output GeoPackage file where trail data will be saved
            rate_limit (float): Seconds to sleep between OSM API requests to respect server limits
            parks (Optional[List[str]]): List of specific park codes to process (e.g., ['YELL', 'GRCA']),
                                       or None to process all parks in the database
            test_limit (Optional[int]): Maximum number of parks to process for testing purposes,
                                      or None for no limit (processes all specified parks)
            log_level (str): Logging verbosity level (e.g., 'INFO', 'DEBUG', 'WARNING', 'ERROR')
            write_db (bool): Whether to write results to PostgreSQL database in addition to file output.
                           If False, only writes to the GeoPackage file.

        Raises:
            SQLAlchemyError: If database connection cannot be established
            ValueError: If invalid log_level is provided
        """
        self.logger: logging.Logger = setup_osm_collector_logging(log_level)
        self.output_gpkg: str = output_gpkg
        self.rate_limit: float = rate_limit
        self.parks: Optional[List[str]] = parks
        self.test_limit: Optional[int] = test_limit
        self.write_db: bool = write_db
        # Always create engine for reading from DB, but only write if write_db is True
        self.engine: Engine = get_postgres_engine()
        self.timestamp: str = datetime.now(timezone.utc).isoformat()
        # Initialize database writer for write operations
        self.db_writer: Optional[DatabaseWriter] = (
            DatabaseWriter(self.engine, self.logger) if write_db else None
        )
        # Track completed parks for resumability - enables restarting interrupted collections
        self.completed_parks: Set[str] = (
            self.get_completed_parks() if write_db else set()
        )

    def load_park_boundaries(self) -> gpd.GeoDataFrame:
        """
        Load park boundary polygons from the database.

        Queries the park_boundaries table and optionally filters to specific parks
        or limits the number of parks for testing purposes.

        Returns:
            gpd.GeoDataFrame: GeoDataFrame containing park codes and boundary geometries

        Raises:
            SQLAlchemyError: If database connection or query fails
        """
        self.logger.info("Loading park boundaries from DB...")
        sql = "SELECT park_code, geometry FROM park_boundaries"
        gdf = gpd.read_postgis(
            sql, self.engine, geom_col="geometry", crs=config.DEFAULT_CRS
        )
        if self.parks:
            gdf = gdf[gdf["park_code"].isin(self.parks)]
        if self.test_limit:
            gdf = gdf.head(self.test_limit)
        self.logger.info(f"Loaded {len(gdf)} park boundaries.")
        return gdf

    def get_completed_parks(self) -> Set[str]:
        """
        Get set of park codes that have already been processed.

        This method queries the osm_hikes table to find which parks already have
        trail data, enabling resumable collection runs. If the table doesn't exist
        or there's an error accessing it, returns an empty set.

        Returns:
            Set[str]: Set of park codes (e.g., {'YELL', 'GRCA'}) that already have
                     trail data in the database. Empty set if no data exists or
                     if write_db is False.

        Note:
            This method only runs when write_db=True. When write_db=False, the
            collector doesn't need to check for completed parks since it's not
            writing to the database.
        """
        if not self.write_db or self.db_writer is None:
            return set()

        return self.db_writer.get_completed_records("osm_hikes", "park_code")

    def query_osm_trails(
        self, polygon: Union[Polygon, MultiPolygon]
    ) -> gpd.GeoDataFrame:
        """
        Query OpenStreetMap for hiking trails within a given polygon boundary.

        Uses the osmnx library to query OSM's Overpass API for features tagged
        as 'path' or 'footway' (common hiking trail tags) within the polygon.
        The query respects OSM's usage policies and includes rate limiting.

        Args:
            polygon (Union[Polygon, MultiPolygon]): Shapely geometry object defining
                                                   the park boundary search area

        Returns:
            gpd.GeoDataFrame: GeoDataFrame containing trail geometries and OSM attributes
                             including osm_id, highway type, name, and geometry. Returns
                             empty GeoDataFrame if no trails found or if the query fails.

        Note:
            This method may take several seconds to complete for large parks due to
            OSM API response times. Network timeouts or OSM server issues will result
            in an empty GeoDataFrame being returned with an error logged.
        """
        try:
            # Validate and repair polygon geometry if needed
            if not polygon.is_valid:
                self.logger.warning("Invalid polygon geometry detected. Attempting to repair...")
                # Try to fix the polygon using buffer(0) which often repairs self-intersections
                polygon = polygon.buffer(0)
                if not polygon.is_valid:
                    self.logger.error("Unable to repair polygon geometry. Skipping OSM query.")
                    return gpd.GeoDataFrame()
                else:
                    self.logger.info("Successfully repaired polygon geometry.")
            
            trails = ox.features.features_from_polygon(
                polygon, tags=config.OSM_TRAIL_TAGS
            )
            if trails.empty:
                return trails
            trails = trails.reset_index()  # Expose OSM index columns
            trails["osm_id"] = (
                trails["osmid"] if "osmid" in trails.columns else trails["id"]
            )
            return trails
        except Exception as e:
            self.logger.error(f"OSM query failed: {e}")
            return gpd.GeoDataFrame()

    def validate_trails(
        self, trails: gpd.GeoDataFrame, park_code: str
    ) -> gpd.GeoDataFrame:
        """
        Validate and clean trail data.

        Args:
            trails (gpd.GeoDataFrame): Raw trail data
            park_code (str): Park code for logging context

        Returns:
            gpd.GeoDataFrame: Validated trail data
        """
        if trails.empty:
            return trails

        initial_count = len(trails)

        # Remove trails with invalid geometries
        valid_geom = trails.geometry.is_valid
        trails = trails[valid_geom]
        if not valid_geom.all():
            self.logger.warning(
                f"Removed {(~valid_geom).sum()} trails with invalid geometries for {park_code}"
            )

        # Remove trails with unrealistic lengths (< 0.01 miles or > 50 miles)
        if "length_mi" in trails.columns:
            reasonable_length = (trails["length_mi"] >= 0.01) & (
                trails["length_mi"] <= 50.0
            )
            trails = trails[reasonable_length]
            if not reasonable_length.all():
                self.logger.warning(
                    f"Removed {(~reasonable_length).sum()} trails with unrealistic lengths for {park_code}"
                )

        # Remove duplicate OSM IDs within this park
        if "osm_id" in trails.columns:
            before_dedup = len(trails)
            trails = trails.drop_duplicates(subset=["osm_id"], keep="first")
            if len(trails) < before_dedup:
                self.logger.warning(
                    f"Removed {before_dedup - len(trails)} duplicate OSM IDs for {park_code}"
                )

        # Log validation summary
        final_count = len(trails)
        if final_count < initial_count:
            self.logger.info(
                f"Validation for {park_code}: {initial_count} → {final_count} trails ({initial_count - final_count} removed)"
            )

        return trails

    def process_trails(
        self, park_code: str, polygon: Union[Polygon, MultiPolygon]
    ) -> gpd.GeoDataFrame:
        """
        Process and clean hiking trail data for a specific park.

        This is the main processing pipeline that downloads trails from OSM, applies
        filtering and validation rules, calculates metrics, and standardizes the data
        format for storage. The process includes:
        1. Query OSM for trail features within park boundary
        2. Filter for linear geometries (LineString/MultiLineString)
        3. Filter for named trails only
        4. Calculate trail lengths in miles using appropriate projection
        5. Add metadata (park code, timestamp, geometry type)
        6. Validate data quality and remove invalid records

        Args:
            park_code (str): National Park Service park code identifier (e.g., 'YELL', 'GRCA')
            polygon (Union[Polygon, MultiPolygon]): Shapely geometry defining the park boundary
                                                   used as the search area for OSM queries

        Returns:
            gpd.GeoDataFrame: Processed trail data with standardized columns including:
                             osm_id, park_code, highway, name, source, length_mi,
                             geometry_type, geometry, and timestamp. Returns empty
                             GeoDataFrame if no valid trails found after processing.

        Note:
            Only trails with names are included in the results, as unnamed paths are
            often service roads or informal tracks rather than established hiking trails.
            Trail lengths are calculated using a projected coordinate system for accuracy.
        """
        trails = self.query_osm_trails(polygon)
        if trails.empty:
            self.logger.warning(f"No trails found for park {park_code}.")
            return gpd.GeoDataFrame(columns=config.OSM_ALL_COLUMNS)

        # Filter for linestrings
        trails = trails[trails.geometry.type.isin(["LineString", "MultiLineString"])]

        # Filter for named trails
        trails = trails[trails["name"].notnull() & (trails["name"].str.strip() != "")]

        # Add geometry_type
        trails["geometry_type"] = trails.geometry.type

        # Compute length in miles
        trails_proj = trails.to_crs(config.OSM_LENGTH_CRS)
        trails["length_mi"] = trails_proj.geometry.length / 1609.34

        # Add park_code
        trails["park_code"] = park_code

        # Add source (from OSM tag if present)
        if "source" not in trails.columns:
            trails["source"] = None

        # Keep only required columns
        trails = trails[
            [
                "osm_id",
                "park_code",
                "highway",
                "name",
                "source",
                "length_mi",
                "geometry_type",
                "geometry",
            ]
        ]

        # Drop rows with any required column missing
        before = len(trails)
        trails = trails.dropna(subset=config.OSM_REQUIRED_COLUMNS)
        after = len(trails)
        if after < before:
            self.logger.warning(
                f"Dropped {before - after} trails with missing required fields for park {park_code}."
            )

        # Validate the data
        trails = self.validate_trails(trails, park_code)

        # CLIP TRAILS TO BOUNDARY (NEW) - with primary key handling
        trails = self.clip_trails_to_boundary(trails, polygon, park_code)

        return trails

    def clip_trails_to_boundary(
        self,
        trails_gdf: gpd.GeoDataFrame,
        boundary_geom,
        park_code: str,
    ) -> gpd.GeoDataFrame:
        """
        Clip OSM trails to exact park boundary and recalculate lengths.

        Args:
            trails_gdf: GeoDataFrame with trail data
            boundary_geom: Park boundary geometry
            park_code: Park code for logging

        Returns:
            Clipped GeoDataFrame with recalculated lengths
        """
        if trails_gdf.empty:
            return trails_gdf

        try:
            original_count = len(trails_gdf)
            clipped_trails = []
            total_clipped_length = 0.0
            
            for idx, trail in trails_gdf.iterrows():
                if trail.geometry.intersects(boundary_geom):
                    # Clip the trail to the boundary
                    clipped_geom = trail.geometry.intersection(boundary_geom)
                    
                    if not clipped_geom.is_empty:
                        # Handle different geometry types that might result from clipping
                        if clipped_geom.geom_type == 'LineString':
                            clipped_geometries = [clipped_geom]
                        elif clipped_geom.geom_type == 'MultiLineString':
                            clipped_geometries = list(clipped_geom.geoms)
                        else:
                            # Skip if clipping resulted in non-linestring geometry
                            continue
                        
                        # Create a trail record for each clipped segment
                        for i, geom in enumerate(clipped_geometries):
                            trail_copy = trail.copy()
                            trail_copy.geometry = geom
                            
                            # CRITICAL: Handle composite primary key for multiple segments
                            # If we have multiple segments, modify the osm_id to make it unique
                            if len(clipped_geometries) > 1:
                                # Generate unique integer ID for segments using hash
                                original_osm_id = trail_copy['osm_id']
                                # Use hash of original_id + segment_index to create unique integer
                                unique_string = f"{original_osm_id}_{i}"
                                # Convert to positive integer using hash (keep within BIGINT range)
                                trail_copy['osm_id'] = abs(hash(unique_string)) % (2**63 - 1)
                            
                            # Recalculate length in miles using projected CRS
                            # Convert geometry to projected CRS for accurate length calculation
                            geom_proj = geom
                            if trails_gdf.crs != config.OSM_LENGTH_CRS:
                                # Create a temporary GeoDataFrame to reproject
                                temp_gdf = gpd.GeoDataFrame([{'geometry': geom}], crs=trails_gdf.crs)
                                temp_gdf_proj = temp_gdf.to_crs(config.OSM_LENGTH_CRS)
                                geom_proj = temp_gdf_proj.geometry.iloc[0]
                            
                            # Calculate length in miles
                            length_miles = geom_proj.length / 1609.34  # Convert meters to miles
                            
                            # Only keep trails that meet minimum length requirement
                            if length_miles >= 0.01:  # OSM minimum length
                                trail_copy['length_mi'] = length_miles
                                clipped_trails.append(trail_copy)
                                total_clipped_length += length_miles
            
            # Create new GeoDataFrame with clipped trails
            if clipped_trails:
                result_gdf = gpd.GeoDataFrame(clipped_trails, crs=trails_gdf.crs)
            else:
                result_gdf = gpd.GeoDataFrame(crs=trails_gdf.crs)
            
            clipped_count = len(result_gdf)
            self.logger.info(
                f"Clipped OSM {park_code}: {original_count} -> {clipped_count} trails "
                f"(total length: {total_clipped_length:.1f} mi)"
            )
            
            return result_gdf

        except Exception as e:
            self.logger.error(f"Error clipping OSM trails for {park_code}: {e}")
            return trails_gdf

    def collect_all_trails(self) -> gpd.GeoDataFrame:
        """
        Collect hiking trails for all specified parks with per-park processing.

        This is the main orchestration method that processes multiple parks sequentially.
        It implements several important features:
        - Resumability: Skips parks that already have data in the database
        - Memory efficiency: Writes data per-park instead of accumulating in memory
        - Rate limiting: Respects OSM server limits with configurable delays
        - Progress tracking: Logs detailed progress for long-running collections
        - Error isolation: Individual park failures don't stop the entire collection

        The method loads park boundaries, filters for specified parks (if any), applies
        test limits (if specified), and processes each park individually. Results are
        written immediately to both file and database to prevent data loss.

        Returns:
            gpd.GeoDataFrame: Combined trail data from all processed parks for final
                             reporting and statistics. This is a summary view - the
                             actual persistent data is written to files and database
                             during processing. Returns empty GeoDataFrame if no trails
                             were collected from any park.

        Note:
            This method can run for hours when processing all parks. Progress is logged
            regularly, and the process can be safely interrupted and resumed later when
            write_db=True, as completed parks will be automatically skipped.
        """
        park_gdf = self.load_park_boundaries()

        # Filter out already completed parks for resumability
        if self.completed_parks:
            initial_count = len(park_gdf)
            park_gdf = park_gdf[~park_gdf["park_code"].isin(self.completed_parks)]
            skipped_count = initial_count - len(park_gdf)
            if skipped_count > 0:
                self.logger.info(f"Skipping {skipped_count} already completed parks")

        if park_gdf.empty:
            self.logger.info("No parks to process (all completed)")
            return gpd.GeoDataFrame(columns=config.OSM_ALL_COLUMNS)

        total_trails_collected = 0
        all_trails_for_summary = []

        for _, row in park_gdf.iterrows():
            park_code = row["park_code"]
            polygon = row["geometry"]
            self.logger.info(f"Processing park {park_code}...")

            trails = self.process_trails(park_code, polygon)

            if not trails.empty:
                # Save immediately to both GPKG and DB
                self.save_to_gpkg(trails, append=True)
                if self.db_writer:
                    self.db_writer.write_osm_hikes(trails, mode="append")

                total_trails_collected += len(trails)
                all_trails_for_summary.append(trails)
                self.logger.info(f"✓ Processed {park_code}: {len(trails)} trails")
            else:
                self.logger.info(f"No valid trails for park {park_code}.")

            # Rate limiting
            import time

            time.sleep(self.rate_limit)

        self.logger.info(
            f"Collection complete: {total_trails_collected} total trails collected"
        )

        # Return combined data for summary purposes
        if all_trails_for_summary:
            result = pd.concat(all_trails_for_summary, ignore_index=True)
            result = gpd.GeoDataFrame(result, crs=config.DEFAULT_CRS)
            return result
        else:
            self.logger.warning("No trails collected for any park.")
            return gpd.GeoDataFrame(columns=config.OSM_ALL_COLUMNS)

    def save_to_gpkg(self, gdf: gpd.GeoDataFrame, append: bool = False) -> None:
        """
        Save trail data to a GeoPackage file with append capability.

        This method handles writing trail data to the output GeoPackage file, with
        support for both creating new files and appending to existing ones. When
        appending, it reads the existing data, combines it with new data, and
        writes the complete dataset back to the file.

        Args:
            gdf (gpd.GeoDataFrame): Trail data to save, containing standardized columns
                                   including geometry, park_code, trail names, etc.
            append (bool): If True, append to existing file by reading current data
                          and combining with new data. If False, overwrite any existing
                          file. Defaults to False.

        Note:
            GeoPackage format is used because it's an open standard, supports large
            datasets efficiently, and maintains spatial indexes automatically. The
            append operation requires reading the entire existing file into memory,
            so very large datasets may need alternative approaches.
        """
        if gdf.empty:
            self.logger.warning("No data to save to GPKG.")
            return

        # Check if file exists and we want to append
        if append and os.path.exists(self.output_gpkg):
            # Read existing data and concatenate
            try:
                existing = gpd.read_file(self.output_gpkg)
                combined = pd.concat([existing, gdf], ignore_index=True)
                combined.to_file(self.output_gpkg, driver="GPKG")
                self.logger.info(
                    f"Appended {len(gdf)} trails to {self.output_gpkg} (total: {len(combined)})"
                )
            except Exception as e:
                self.logger.error(
                    f"Failed to append to GPKG: {e}. Overwriting instead."
                )
                gdf.to_file(self.output_gpkg, driver="GPKG")
                self.logger.info(f"Saved {len(gdf)} trails to {self.output_gpkg}")
        else:
            gdf.to_file(self.output_gpkg, driver="GPKG")
            self.logger.info(f"Saved {len(gdf)} trails to {self.output_gpkg}")

    def run(self) -> None:
        """
        Execute the complete trail collection pipeline.

        This is the main entry point that orchestrates the entire collection process
        from start to finish. It handles initialization, processing, and cleanup
        while providing comprehensive logging and error handling.

        The complete workflow includes:
        1. Initialize output files (remove existing if not resuming)
        2. Process all specified parks sequentially with rate limiting
        3. Write data incrementally to prevent memory issues and data loss
        4. Log comprehensive summary statistics and completion status
        5. Handle both file and database output based on configuration

        The method is designed to be robust for long-running operations and provides
        detailed progress information throughout the collection process.

        Note:
            This method can run for several hours when processing all parks. The
            process logs detailed progress and can be safely interrupted and resumed
            when write_db=True, as completed parks will be automatically skipped.
        """
        self.logger.info("Starting OSM hiking trails collection...")

        # Initialize output file if not appending
        if os.path.exists(self.output_gpkg) and not self.completed_parks:
            self.logger.info(f"Removing existing output file: {self.output_gpkg}")
            os.remove(self.output_gpkg)

        # Collect all trails (writes per-park internally)
        summary_gdf = self.collect_all_trails()

        # Log final summary
        if not summary_gdf.empty:
            self.logger.info(
                f"Collection summary: {len(summary_gdf)} trails across {summary_gdf['park_code'].nunique()} parks"
            )
            self.logger.info(f"Output saved to: {self.output_gpkg}")
            if self.write_db:
                self.logger.info("Data also saved to database")
        else:
            self.logger.warning("No trails were collected")

        self.logger.info("OSM hikes collection pipeline completed successfully")


# --- CLI ---
def main() -> None:
    """
    Main function for command-line execution of the OSM hiking trails collector.

    This function provides the command-line interface for the OSM trails collector,
    parsing arguments and configuring the collection process. It supports flexible
    configuration options for different use cases from testing to production runs.

    The function handles argument parsing, input validation, collector initialization,
    and execution orchestration. It's designed to be the primary entry point for
    both interactive use and automated/scripted execution.

    Command-line Arguments:
        --write-db: Write results to the PostgreSQL database in addition to file output.
                   When enabled, supports resumable collection runs.
        --output-gpkg: Path for the output GeoPackage file (default from config).
                      File will be created if it doesn't exist.
        --rate-limit: Seconds to sleep between OSM API requests (default: 1.0).
                     Higher values are more respectful to OSM servers but slower.
        --parks: Comma-separated list of park codes to process (e.g., 'YELL,GRCA').
                Optional - processes all parks if not specified.
        --test-limit: Maximum number of parks to process for testing purposes.
                     Useful for validating configuration before full runs.
        --log-level: Logging verbosity level ('DEBUG', 'INFO', 'WARNING', 'ERROR').
                    Controls both console and file logging output.

    Example Usage:
        # Process all parks and write to database
        python osm_hikes_collector.py --write-db

        # Test with just 3 parks
        python osm_hikes_collector.py --test-limit 3 --log-level DEBUG

        # Process specific parks only
        python osm_hikes_collector.py --parks YELL,GRCA --write-db
    """
    parser = argparse.ArgumentParser(description="OSM Park Hikes Collector (Stage 3)")
    parser.add_argument(
        "--write-db", action="store_true", help="Write results to the database"
    )
    parser.add_argument(
        "--output-gpkg",
        default=config.OSM_DEFAULT_OUTPUT_GPKG,
        help="Output GeoPackage file path",
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=config.OSM_DEFAULT_RATE_LIMIT,
        help="Seconds to sleep between OSM queries",
    )
    parser.add_argument(
        "--parks",
        type=str,
        help="Comma-separated list of park codes to process (optional)",
    )
    parser.add_argument(
        "--test-limit", type=int, help="Limit to first N parks (for testing)"
    )
    parser.add_argument(
        "--log-level", default=config.LOG_LEVEL, help="Logging level (default: INFO)"
    )
    args = parser.parse_args()

    # Validate configuration for database operations (OSM collector doesn't use NPS API)
    config.validate_for_database_operations()

    parks = args.parks.split(",") if args.parks else None

    collector = OSMHikesCollector(
        output_gpkg=args.output_gpkg,
        rate_limit=args.rate_limit,
        parks=parks,
        test_limit=args.test_limit,
        log_level=args.log_level,
        write_db=args.write_db,
    )
    collector.run()


if __name__ == "__main__":
    main()

"""
OpenStreetMap Hiking Trails Collector for National Parks

This script collects hiking trail data from OpenStreetMap (OSM) for National Parks
by querying OSM's Overpass API within park boundary polygons. It downloads trail
geometries tagged as 'path' or 'footway', processes them to extract relevant
attributes, and saves the results to both GeoPackage files and PostgreSQL database.

The collector focuses on named hiking trails and computes trail lengths in miles
using proper geographic projections. It includes rate limiting to be respectful
to OSM servers and comprehensive error handling for robust data collection.
"""

# Standard library imports
import argparse
import os
import sys
from datetime import datetime, timezone
from typing import List, Optional

# Third-party imports
import geopandas as gpd
import osmnx as ox
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv

# Load .env before local imports that need env vars
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# Local application imports
from config.settings import config
from nps_db_writer import get_postgres_engine

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
    ):
        """
        Initialize the OSM hikes collector with configuration parameters.

        Args:
            output_gpkg (str): Path to output GeoPackage file
            rate_limit (float): Seconds to sleep between OSM API requests
            parks (Optional[List[str]]): List of specific park codes to process, or None for all parks
            test_limit (Optional[int]): Maximum number of parks to process for testing, or None for no limit
            log_level (str): Logging level (e.g., 'INFO', 'DEBUG', 'WARNING')
            write_db (bool): Whether to write results to the database in addition to file output
        """
        self.logger = setup_osm_collector_logging(log_level)
        self.output_gpkg = output_gpkg
        self.rate_limit = rate_limit
        self.parks = parks
        self.test_limit = test_limit
        self.write_db = write_db
        # Always create engine for reading from DB, but only write if write_db is True
        self.engine = get_postgres_engine()
        self.timestamp = datetime.now(timezone.utc).isoformat()
        # Track completed parks for resumability
        self.completed_parks = self.get_completed_parks() if write_db else set()

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
        gdf = gpd.read_postgis(sql, self.engine, geom_col="geometry", crs=config.DEFAULT_CRS)
        if self.parks:
            gdf = gdf[gdf["park_code"].isin(self.parks)]
        if self.test_limit:
            gdf = gdf.head(self.test_limit)
        self.logger.info(f"Loaded {len(gdf)} park boundaries.")
        return gdf

    def get_completed_parks(self) -> set:
        """
        Get set of park codes that have already been processed.
        
        Returns:
            set: Set of park codes with existing trail data
        """
        if not self.write_db or self.engine is None:
            return set()
        
        try:
            sql = "SELECT DISTINCT park_code FROM park_hikes"
            result = pd.read_sql(sql, self.engine)
            completed = set(result['park_code'].tolist())
            if completed:
                self.logger.info(f"Found {len(completed)} parks with existing trail data: {sorted(completed)}")
            return completed
        except Exception as e:
            self.logger.warning(f"Could not check completed parks: {e}")
            return set()
    
    def query_osm_trails(self, polygon) -> gpd.GeoDataFrame:
        """
        Query OpenStreetMap for hiking trails within a given polygon boundary.

        Uses the osmnx library to query OSM's Overpass API for features tagged
        as 'path' or 'footway' (common hiking trail tags) within the polygon.

        Args:
            polygon: Shapely polygon or similar geometry object defining the search area

        Returns:
            gpd.GeoDataFrame: GeoDataFrame containing trail geometries and OSM attributes,
                             or empty GeoDataFrame if no trails found or query fails
        """
        try:
            trails = ox.features.features_from_polygon(polygon, tags=config.OSM_TRAIL_TAGS)
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

    def validate_trails(self, trails: gpd.GeoDataFrame, park_code: str) -> gpd.GeoDataFrame:
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
            self.logger.warning(f"Removed {(~valid_geom).sum()} trails with invalid geometries for {park_code}")
        
        # Remove trails with unrealistic lengths (< 0.01 miles or > 50 miles)
        if 'length_mi' in trails.columns:
            reasonable_length = (trails['length_mi'] >= 0.01) & (trails['length_mi'] <= 50.0)
            trails = trails[reasonable_length]
            if not reasonable_length.all():
                self.logger.warning(f"Removed {(~reasonable_length).sum()} trails with unrealistic lengths for {park_code}")
        
        # Remove duplicate OSM IDs within this park
        if 'osm_id' in trails.columns:
            before_dedup = len(trails)
            trails = trails.drop_duplicates(subset=['osm_id'], keep='first')
            if len(trails) < before_dedup:
                self.logger.warning(f"Removed {before_dedup - len(trails)} duplicate OSM IDs for {park_code}")
        
        # Log validation summary
        final_count = len(trails)
        if final_count < initial_count:
            self.logger.info(f"Validation for {park_code}: {initial_count} → {final_count} trails ({initial_count - final_count} removed)")
        
        return trails
    
    def process_trails(self, park_code: str, polygon) -> gpd.GeoDataFrame:
        """
        Process and clean hiking trail data for a specific park.

        Downloads trails from OSM, filters for linear geometries and named trails,
        calculates trail lengths in miles, and adds metadata including park code
        and timestamp. Removes any records missing required fields.

        Args:
            park_code (str): National Park Service park code (e.g., 'YELL', 'GRCA')
            polygon: Shapely polygon defining the park boundary

        Returns:
            gpd.GeoDataFrame: Processed trail data with standardized columns and metadata,
                             or empty GeoDataFrame if no valid trails found
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
        
        # Add park_code and timestamp
        trails["park_code"] = park_code
        trails["timestamp"] = self.timestamp
        
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
                "timestamp",
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
        
        return trails

    def collect_all_trails(self) -> gpd.GeoDataFrame:
        """
        Collect hiking trails for all specified parks with per-park processing.

        Iterates through all park boundaries, downloads and processes trails for each,
        and writes results immediately to avoid memory issues. Includes rate limiting
        between requests and resumability by skipping completed parks.

        Returns:
            gpd.GeoDataFrame: Final combined trail data for reporting purposes,
                             or empty GeoDataFrame if no trails collected
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
                if self.write_db:
                    self.save_to_db(trails)
                
                total_trails_collected += len(trails)
                all_trails_for_summary.append(trails)
                self.logger.info(f"✓ Processed {park_code}: {len(trails)} trails")
            else:
                self.logger.info(f"No valid trails for park {park_code}.")
            
            # Rate limiting
            import time
            time.sleep(self.rate_limit)
        
        self.logger.info(f"Collection complete: {total_trails_collected} total trails collected")
        
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
        Save trail data to a GeoPackage file.

        Args:
            gdf (gpd.GeoDataFrame): Trail data to save
            append (bool): If True, append to existing file, otherwise overwrite
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
                self.logger.info(f"Appended {len(gdf)} trails to {self.output_gpkg} (total: {len(combined)})")
            except Exception as e:
                self.logger.error(f"Failed to append to GPKG: {e}. Overwriting instead.")
                gdf.to_file(self.output_gpkg, driver="GPKG")
                self.logger.info(f"Saved {len(gdf)} trails to {self.output_gpkg}")
        else:
            gdf.to_file(self.output_gpkg, driver="GPKG")
            self.logger.info(f"Saved {len(gdf)} trails to {self.output_gpkg}")

    def create_db_table(self) -> None:
        """
        Create the park_hikes table in the database if it doesn't exist.

        Creates a table with proper PostGIS geometry columns and foreign key
        constraints linking to the park_boundaries table.

        Raises:
            SQLAlchemyError: If table creation fails
        """
        sql = f"""
        CREATE TABLE IF NOT EXISTS park_hikes (
            osm_id BIGINT NOT NULL,
            park_code VARCHAR NOT NULL,
            highway VARCHAR NOT NULL,
            name VARCHAR,
            source VARCHAR,
            length_mi DOUBLE PRECISION NOT NULL,
            geometry_type VARCHAR NOT NULL,
            geometry geometry(LINESTRING, 4326) NOT NULL,
            timestamp TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (park_code, osm_id),
            FOREIGN KEY (park_code) REFERENCES park_boundaries(park_code)
        );
        """
        with self.engine.begin() as conn:
            conn.execute(text(sql))
        self.logger.info("Ensured park_hikes table exists in DB.")

    def save_to_db(self, gdf: gpd.GeoDataFrame) -> None:
        """
        Save trail data to the PostgreSQL database using proper PostGIS integration.

        Creates the park_hikes table if needed and inserts trail data with proper
        PostGIS geometry handling using geopandas.to_postgis().

        Args:
            gdf (gpd.GeoDataFrame): Trail data to save

        Raises:
            SQLAlchemyError: If database operations fail
        """
        if gdf.empty:
            self.logger.warning("No data to save to DB.")
            return
            
        self.create_db_table()
        
        try:
            # Use geopandas to_postgis for proper PostGIS integration
            gdf.to_postgis(
                "park_hikes", 
                self.engine, 
                if_exists="append", 
                index=False
            )
            self.logger.info(f"Saved {len(gdf)} trails to park_hikes table in DB.")
        except Exception as e:
            self.logger.error(f"Failed to save trails to database: {e}")
            raise

    def run(self) -> None:
        """
        Execute the complete trail collection pipeline.

        Orchestrates the full process: loads park boundaries, collects trails
        from OSM with per-park writing for efficiency and resumability.
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
            self.logger.info(f"Collection summary: {len(summary_gdf)} trails across {summary_gdf['park_code'].nunique()} parks")
            self.logger.info(f"Output saved to: {self.output_gpkg}")
            if self.write_db:
                self.logger.info("Data also saved to database")
        else:
            self.logger.warning("No trails were collected")


# --- CLI ---
def main():
    """
    Main function for command-line execution of the OSM hiking trails collector.

    Parses command-line arguments to configure the collector and executes the
    complete trail collection pipeline. Supports various options for customizing
    the collection process including park filtering, rate limiting, and output formats.

    Command-line Arguments:
        --write-db: Write results to the PostgreSQL database in addition to file output
        --output-gpkg: Path for the output GeoPackage file (default: park_hikes.gpkg)
        --rate-limit: Seconds to sleep between OSM API requests (default: 1.0)
        --parks: Comma-separated list of park codes to process (optional)
        --test-limit: Maximum number of parks to process for testing (optional)
        --log-level: Logging verbosity level (default: INFO)
    """
    parser = argparse.ArgumentParser(description="OSM Park Hikes Collector (Stage 3)")
    parser.add_argument(
        "--write-db", action="store_true", help="Write results to the database"
    )
    parser.add_argument(
        "--output-gpkg", default=config.OSM_DEFAULT_OUTPUT_GPKG, help="Output GeoPackage file path"
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

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
import logging
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

# --- Configuration ---
DEFAULT_OUTPUT_GPKG = "park_hikes.gpkg"
DEFAULT_RATE_LIMIT = 1.0  # seconds
DEFAULT_LOG_LEVEL = "INFO"
REQUIRED_COLUMNS = [
    "osm_id",
    "park_code",
    "highway",
    "geometry",
    "geometry_type",
    "length_mi",
]
ALL_COLUMNS = [
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
STANDARD_CRS = config.DEFAULT_CRS
LENGTH_CRS = "EPSG:5070"  # NAD83 / Conus Albers (meters)


# --- Logging Setup ---
def setup_logging(log_level: str):
    """
    Configure logging for the application.

    Args:
        log_level (str): Logging level (e.g., 'INFO', 'DEBUG', 'WARNING')
    """
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


# --- Main Collector Class ---
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
        setup_logging(log_level)
        self.output_gpkg = output_gpkg
        self.rate_limit = rate_limit
        self.parks = parks
        self.test_limit = test_limit
        self.write_db = write_db
        # Always create engine for reading from DB, but only write if write_db is True
        self.engine = get_postgres_engine()
        self.timestamp = datetime.now(timezone.utc).isoformat()

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
        logging.info("Loading park boundaries from DB...")
        sql = "SELECT park_code, geometry FROM park_boundaries"
        gdf = gpd.read_postgis(sql, self.engine, geom_col="geometry", crs=STANDARD_CRS)
        if self.parks:
            gdf = gdf[gdf["park_code"].isin(self.parks)]
        if self.test_limit:
            gdf = gdf.head(self.test_limit)
        logging.info(f"Loaded {len(gdf)} park boundaries.")
        return gdf

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
        tags = {"highway": ["path", "footway"]}
        try:
            trails = ox.features.features_from_polygon(polygon, tags=tags)
            if trails.empty:
                return trails
            trails = trails.reset_index()  # Expose OSM index columns
            trails["osm_id"] = (
                trails["osmid"] if "osmid" in trails.columns else trails["id"]
            )
            return trails
        except Exception as e:
            logging.error(f"OSM query failed: {e}")
            return gpd.GeoDataFrame()

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
            logging.warning(f"No trails found for park {park_code}.")
            return gpd.GeoDataFrame(columns=ALL_COLUMNS)
        # Filter for linestrings
        trails = trails[trails.geometry.type.isin(["LineString", "MultiLineString"])]
        # Filter for named trails
        trails = trails[trails["name"].notnull() & (trails["name"].str.strip() != "")]
        # Add geometry_type
        trails["geometry_type"] = trails.geometry.type
        # Compute length in miles
        trails_proj = trails.to_crs(LENGTH_CRS)
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
        trails = trails.dropna(subset=REQUIRED_COLUMNS)
        after = len(trails)
        if after < before:
            logging.warning(
                f"Dropped {before - after} trails with missing required fields for park {park_code}."
            )
        return trails

    def collect_all_trails(self) -> gpd.GeoDataFrame:
        """
        Collect hiking trails for all specified parks.

        Iterates through all park boundaries, downloads and processes trails for each,
        and combines results into a single GeoDataFrame. Includes rate limiting
        between requests to be respectful to OSM servers.

        Returns:
            gpd.GeoDataFrame: Combined trail data for all parks with consistent schema,
                             or empty GeoDataFrame if no trails collected
        """
        park_gdf = self.load_park_boundaries()
        all_trails = []
        for idx, row in park_gdf.iterrows():
            park_code = row["park_code"]
            polygon = row["geometry"]
            logging.info(f"Processing park {park_code}...")
            trails = self.process_trails(park_code, polygon)
            if not trails.empty:
                all_trails.append(trails)
            else:
                logging.info(f"No valid trails for park {park_code}.")
            import time

            time.sleep(self.rate_limit)
        if all_trails:
            result = pd.concat(all_trails, ignore_index=True)
            result = result.set_crs(STANDARD_CRS)
            logging.info(f"Total trails collected: {len(result)}")
            return result
        else:
            logging.warning("No trails collected for any park.")
            return gpd.GeoDataFrame(columns=ALL_COLUMNS)

    def save_to_gpkg(self, gdf: gpd.GeoDataFrame) -> None:
        """
        Save trail data to a GeoPackage file.

        Args:
            gdf (gpd.GeoDataFrame): Trail data to save
        """
        if gdf.empty:
            logging.warning("No data to save to GPKG.")
            return
        gdf.to_file(self.output_gpkg, driver="GPKG")
        logging.info(f"Saved trails to {self.output_gpkg}")

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
        logging.info("Ensured park_hikes table exists in DB.")

    def save_to_db(self, gdf: gpd.GeoDataFrame) -> None:
        """
        Save trail data to the PostgreSQL database.

        Creates the park_hikes table if needed and inserts trail data with proper
        PostGIS geometry handling. Converts geometry to WKT format for database storage.

        Args:
            gdf (gpd.GeoDataFrame): Trail data to save

        Raises:
            SQLAlchemyError: If database operations fail
        """
        if gdf.empty:
            logging.warning("No data to save to DB.")
            return
        self.create_db_table()
        # Use SQLAlchemy to write to DB
        gdf = gdf.copy()
        gdf["geometry"] = gdf["geometry"].apply(lambda geom: geom.wkt)
        # Use pandas to_sql for non-geometry columns, then update geometry
        non_geom_cols = [col for col in gdf.columns if col != "geometry"]
        gdf[non_geom_cols].to_sql(
            "park_hikes", self.engine, if_exists="append", index=False, method="multi"
        )
        # Update geometry using PostGIS function (if needed)
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                UPDATE park_hikes
                SET geometry = ST_GeomFromText(geometry, 4326)
                WHERE geometry_type IN ('LineString', 'MultiLineString');
            """
                )
            )
        logging.info("Saved trails to park_hikes table in DB.")

    def run(self) -> None:
        """
        Execute the complete trail collection pipeline.

        Orchestrates the full process: loads park boundaries, collects trails
        from OSM, saves to GeoPackage file, and optionally saves to database.
        """
        gdf = self.collect_all_trails()
        self.save_to_gpkg(gdf)
        if self.write_db and self.engine is not None:
            self.save_to_db(gdf)


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
        "--output-gpkg", default=DEFAULT_OUTPUT_GPKG, help="Output GeoPackage file path"
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=DEFAULT_RATE_LIMIT,
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
        "--log-level", default=DEFAULT_LOG_LEVEL, help="Logging level (default: INFO)"
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

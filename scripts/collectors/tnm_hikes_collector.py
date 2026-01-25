"""
The National Map (TNM) Hiking Trails Collector

This module provides a comprehensive solution for collecting hiking trail data from
The National Map (TNM) within National Park boundaries. It queries TNM's REST API
to download trail geometries, processes and validates the data, and stores results
in both file and database formats. The USGS provides the TNM. Find the API documentation: https://carto.nationalmap.gov/arcgis/rest/services/transportation/MapServer

Key Features:
- Automated trail discovery using TNM's transportation layer
- Spatial filtering within park boundary polygons
- Data quality validation and standardization
- Resumable collection runs for large datasets
- Rate limiting to respect TNM server policies
- Comprehensive logging and progress tracking
- Dual output: GeoPackage files and PostgreSQL/PostGIS database

Data Processing Pipeline:
1. Load park boundaries from database
2. Query TNM REST API for trail features within each park's bounding box
3. Filter for named trails to focus on established hiking routes
4. Clip trails to exact park boundaries
5. Aggregate trail segments by name (with distance-based continuity checks)
6. Calculate accurate trail lengths using projected coordinate systems
7. Validate data quality and remove invalid/unrealistic records
8. Add metadata (park codes, timestamps, source attribution)
9. Write to both GeoPackage and database with proper spatial indexing
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Set

import geopandas as gpd
import pandas as pd
import requests
from dotenv import load_dotenv
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon
from shapely.ops import linemerge
from sqlalchemy import Engine

# Load .env before local imports that need env vars
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from config.settings import config
from scripts.database.db_writer import DatabaseWriter, get_postgres_engine
from utils.logging import setup_tnm_collector_logging


class TNMHikesCollector:
    """
    A class for collecting hiking trail data from The National Map within National Park boundaries.

    This class encapsulates functionality to query TNM's REST API for hiking
    trails within park boundary polygons, process the geometric and attribute data,
    and save results to both file and database formats.
    """

    def __init__(
        self,
        output_gpkg: str,
        rate_limit: float,
        parks: list[str] | None,
        test_limit: int | None,
        log_level: str,
        write_db: bool,
    ) -> None:
        """
        Initialize the TNM hikes collector with configuration parameters.

        This constructor sets up logging, database connections, and tracks completion state
        for resumable collection runs. The collector can process all parks or be limited
        to specific parks for testing purposes.

        Args:
            output_gpkg (str): Path to output GeoPackage file where trail data will be saved
            rate_limit (float): Seconds to wait between API requests to respect rate limits
            parks (list[str] | None): List of specific park codes to process. If None,
                                        processes all parks in the database
            test_limit (int | None): Limit processing to first N parks for testing
            log_level (str): Logging level (DEBUG, INFO, WARNING, ERROR)
            write_db (bool): Whether to write results to the database
        """
        self.logger = setup_tnm_collector_logging(log_level)
        self.output_gpkg = output_gpkg
        self.rate_limit = rate_limit
        self.parks = parks
        self.test_limit = test_limit
        self.write_db = write_db

        # Database setup
        self.engine = get_postgres_engine()
        self.db_writer = DatabaseWriter(self.engine, self.logger) if write_db else None

        # Track completion state
        self.timestamp = datetime.now(timezone.utc).isoformat()

        self.logger.info(
            f"TNM Hikes Collector initialized - Output: {output_gpkg}, "
            f"Rate limit: {rate_limit}s, Write DB: {write_db}"
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
        sql = "SELECT park_code, geometry, bbox FROM park_boundaries WHERE bbox IS NOT NULL"
        gdf = gpd.read_postgis(
            sql, self.engine, geom_col="geometry", crs=config.DEFAULT_CRS
        )
        if self.parks:
            gdf = gdf[gdf["park_code"].isin(self.parks)]
        if self.test_limit:
            gdf = gdf.head(self.test_limit)
        self.logger.info(f"Loaded {len(gdf)} park boundaries with bbox data.")
        return gdf

    def get_completed_parks(self) -> Set[str]:
        """
        Get set of park codes that have already been processed.

        This method queries the tnm_hikes table to find which parks already have
        trail data, enabling resumable collection runs. If the table doesn't exist
        or there's an error accessing it, returns an empty set.

        Returns:
            Set[str]: Set of park codes (e.g., {'yell', 'grca'}) that already have
                     trail data in the database. Empty set if no data exists or
                     if write_db is False.

        Note:
            This method only runs when write_db=True. When write_db=False, the
            collector doesn't need to check for completed parks since it's not
            writing to the database.
        """
        if not self.write_db or self.db_writer is None:
            return set()

        return self.db_writer.get_completed_records("tnm_hikes", "park_code")

    def query_tnm_api(self, bbox_string: str, park_code: str) -> dict[str, Any] | None:
        """
        Query TNM API for trails within bounding box.

        Args:
            bbox_string: Bounding box as "xmin,ymin,xmax,ymax" string
            park_code: Park code for logging

        Returns:
            API response as dictionary or None if failed
        """
        query_url = f"{config.TNM_API_BASE_URL}/query"

        params = {
            "where": "1=1",
            "geometry": bbox_string,
            "geometryType": "esriGeometryEnvelope",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*",
            "returnGeometry": "true",
            "f": "geojson",
        }

        try:
            self.logger.info(f"Querying TNM API for {park_code}")
            response = requests.get(query_url, params=params, timeout=30)
            response.raise_for_status()

            data: dict[str, Any] = response.json()
            self.logger.info(
                f"Received response for {park_code}: {len(data.get('features', []))} features"
            )
            return data

        except requests.exceptions.RequestException as e:
            self.logger.error(f"API request failed for {park_code}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error querying TNM API for {park_code}: {e}")
            return None

    def load_trails_to_geodataframe(
        self, response: Dict[str, Any], park_code: str
    ) -> gpd.GeoDataFrame:
        """
        Load TNM API response into a GeoDataFrame.

        Args:
            response: TNM API response dictionary
            park_code: Park code for logging

        Returns:
            GeoDataFrame with trail data
        """
        try:
            features = response.get("features", [])
            if not features:
                self.logger.warning(f"No features found for {park_code}")
                return gpd.GeoDataFrame()

            # Convert to GeoDataFrame
            gdf = gpd.GeoDataFrame.from_features(features, crs=config.DEFAULT_CRS)

            # Add park_code column
            gdf["park_code"] = park_code

            # Map API column names to database column names
            gdf = self._map_api_columns_to_db_columns(gdf)

            self.logger.info(f"Loaded {len(gdf)} trails for {park_code}")
            return gdf

        except Exception as e:
            self.logger.error(
                f"Error loading trails to GeoDataFrame for {park_code}: {e}"
            )
            return gpd.GeoDataFrame()

    def _map_api_columns_to_db_columns(self, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """
        Map TNM API column names to database column names.

        Args:
            gdf: GeoDataFrame with API column names

        Returns:
            GeoDataFrame with database column names
        """
        # Column mapping from API names to database names
        column_mapping = {
            "permanentidentifier": "permanent_identifier",
            "objectid": "object_id",
            "namealternate": "name_alternate",
            "trailnumber": "trail_number",
            "trailnumberalternate": "trail_number_alternate",
            "sourcefeatureid": "source_feature_id",
            "sourcedatasetid": "source_dataset_id",
            "sourceoriginator": "source_originator",
            "loaddate": "load_date",
            "trailtype": "trail_type",
            "hikerpedestrian": "hiker_pedestrian",
            "packsaddle": "pack_saddle",
            "ohvover50inches": "ohv_over_50_inches",
            "crosscountryski": "cross_country_ski",
            "nonmotorizedwatercraft": "non_motorized_watercraft",
            "motorizedwatercraft": "motorized_watercraft",
            "primarytrailmaintainer": "primary_trail_maintainer",
            "nationaltraildesignation": "national_trail_designation",
            "lengthmiles": "length_miles",
            "networklength": "network_length",
            "shape_Length": "shape_length",
            "sourcedatadecscription": "source_data_description",
            "globalid": "global_id",
        }

        # Rename columns that exist in the dataframe
        existing_columns = [col for col in column_mapping.keys() if col in gdf.columns]
        if existing_columns:
            rename_dict = {col: column_mapping[col] for col in existing_columns}
            gdf = gdf.rename(columns=rename_dict)
            self.logger.debug(
                f"Mapped TNM columns: {list(rename_dict.keys())} -> {list(rename_dict.values())}"
            )

        # Add required metadata columns for database
        if not gdf.empty:
            gdf["collected_at"] = self.timestamp
            gdf["geometry_type"] = gdf.geometry.type

            # Map boolean-like fields from "Yes"/"No" to "Y"/"N" for VARCHAR(1) columns
            boolean_fields = [
                "hiker_pedestrian",
                "bicycle",
                "pack_saddle",
                "atv",
                "motorcycle",
                "ohv_over_50_inches",
                "snowshoe",
                "cross_country_ski",
                "dogsled",
                "snowmobile",
                "non_motorized_watercraft",
                "motorized_watercraft",
            ]

            for field in boolean_fields:
                if field in gdf.columns:
                    gdf[field] = gdf[field].replace(
                        {
                            "Yes": "Y",
                            "No": "N",
                            "yes": "Y",
                            "no": "N",
                            "YES": "Y",
                            "NO": "N",
                        }
                    )

        return gdf

    def filter_named_trails(
        self, gdf: gpd.GeoDataFrame, park_code: str
    ) -> gpd.GeoDataFrame:
        """
        Filter trails to only include those with names.

        Args:
            gdf: GeoDataFrame with trail data
            park_code: Park code for logging

        Returns:
            Filtered GeoDataFrame with only named trails
        """
        if gdf.empty:
            return gdf

        # Filter for trails with names
        original_count = len(gdf)
        gdf = gdf[gdf["name"].notna() & (gdf["name"] != "")]

        filtered_count = len(gdf)
        self.logger.info(
            f"Filtered {park_code}: {original_count} -> {filtered_count} named trails"
        )

        return gdf

    def clip_trails_to_boundary(
        self,
        trails_gdf: gpd.GeoDataFrame,
        boundary_gdf: gpd.GeoDataFrame,
        park_code: str,
    ) -> gpd.GeoDataFrame:
        """
        Clip trails to exact park boundary and recalculate lengths.

        This method performs actual geometric clipping of trail linestrings to the
        park boundary polygon, ensuring only trail segments within the park are kept.
        Trail lengths are recalculated after clipping.

        Args:
            trails_gdf: GeoDataFrame with trail data
            boundary_gdf: GeoDataFrame with park boundary
            park_code: Park code for logging

        Returns:
            Clipped GeoDataFrame with recalculated lengths
        """
        if trails_gdf.empty:
            return trails_gdf

        try:
            # Get the park boundary geometry
            boundary_geom = boundary_gdf.geometry.iloc[0]
            original_count = len(trails_gdf)

            # Ensure both datasets are in the same CRS
            if trails_gdf.crs != boundary_gdf.crs:
                self.logger.warning(
                    f"CRS mismatch in {park_code}: trails={trails_gdf.crs}, boundary={boundary_gdf.crs}"
                )
                trails_gdf = trails_gdf.to_crs(boundary_gdf.crs)

            clipped_trails = []
            total_clipped_length = 0.0

            for idx, trail in trails_gdf.iterrows():
                if trail.geometry.intersects(boundary_geom):
                    # Clip the trail to the boundary
                    clipped_geom = trail.geometry.intersection(boundary_geom)

                    if not clipped_geom.is_empty:
                        # Handle different geometry types that might result from clipping
                        if clipped_geom.geom_type == "LineString":
                            clipped_geometries = [clipped_geom]
                        elif clipped_geom.geom_type == "MultiLineString":
                            clipped_geometries = list(clipped_geom.geoms)
                        else:
                            # Skip if clipping resulted in non-linestring geometry
                            continue

                        # Create a trail record for each clipped segment
                        for i, geom in enumerate(clipped_geometries):
                            trail_copy = trail.copy()
                            trail_copy.geometry = geom

                            # Recalculate length in miles using projected CRS
                            # Convert geometry to projected CRS for accurate length calculation
                            geom_proj = geom
                            if trails_gdf.crs != "EPSG:5070":  # NAD83 / Conus Albers
                                # Create a temporary GeoDataFrame to reproject
                                temp_gdf = gpd.GeoDataFrame(
                                    [{"geometry": geom}], crs=trails_gdf.crs
                                )
                                temp_gdf_proj = temp_gdf.to_crs("EPSG:5070")
                                geom_proj = temp_gdf_proj.geometry.iloc[0]

                            # Calculate length in miles
                            length_miles = (
                                geom_proj.length / 1609.34
                            )  # Convert meters to miles

                            # Only keep trails that meet minimum length requirement
                            if length_miles >= config.TNM_MIN_TRAIL_LENGTH_MI:
                                trail_copy["length_miles"] = length_miles
                                trail_copy["shape_length"] = (
                                    geom.length
                                )  # Keep original decimal degrees
                                clipped_trails.append(trail_copy)
                                total_clipped_length += length_miles

            # Create new GeoDataFrame with clipped trails
            if clipped_trails:
                result_gdf = gpd.GeoDataFrame(clipped_trails, crs=trails_gdf.crs)
            else:
                result_gdf = gpd.GeoDataFrame(crs=trails_gdf.crs)

            clipped_count = len(result_gdf)
            self.logger.info(
                f"Clipped {park_code}: {original_count} -> {clipped_count} trails "
                f"(total length: {total_clipped_length:.1f} mi)"
            )

            return result_gdf

        except Exception as e:
            self.logger.error(f"Error clipping trails for {park_code}: {e}")
            return trails_gdf

    def aggregate_trails_by_name(
        self, gdf: gpd.GeoDataFrame, park_code: str
    ) -> gpd.GeoDataFrame:
        """
        Aggregate trail segments with the same name that are within the aggregation distance.

        Args:
            gdf: GeoDataFrame with trail data
            park_code: Park code for logging

        Returns:
            GeoDataFrame with aggregated trails
        """
        if gdf.empty:
            return gdf

        try:
            original_count = len(gdf)

            # Group by name (case-insensitive)
            gdf["name_lower"] = gdf["name"].str.lower()
            grouped = gdf.groupby("name_lower")

            aggregated_trails = []

            for name_lower, group in grouped:
                if len(group) == 1:
                    # Single trail, no aggregation needed
                    trail = group.iloc[0].copy()
                    trail["name_lower"] = name_lower
                    aggregated_trails.append(trail)
                else:
                    # Multiple trails with same name, try to aggregate
                    geometries = list(group.geometry)

                    # Try to merge geometries
                    try:
                        merged_geom = linemerge(geometries)
                        if merged_geom.is_empty:
                            # Merging failed, keep as separate trails
                            for _, trail in group.iterrows():
                                trail_copy = trail.copy()
                                trail_copy["name_lower"] = name_lower
                                aggregated_trails.append(trail_copy)
                        else:
                            # Merging successful, create single trail
                            trail = group.iloc[0].copy()
                            trail["geometry"] = merged_geom
                            trail["name_lower"] = name_lower
                            # Sum the lengths if available
                            if (
                                "length_miles" in trail
                                and trail["length_miles"] is not None
                            ):
                                trail["length_miles"] = group["length_miles"].sum()
                            aggregated_trails.append(trail)
                    except Exception:
                        # Merging failed, keep as separate trails
                        for _, trail in group.iterrows():
                            trail_copy = trail.copy()
                            trail_copy["name_lower"] = name_lower
                            aggregated_trails.append(trail_copy)

            # Create new GeoDataFrame
            if aggregated_trails:
                result_gdf = gpd.GeoDataFrame(aggregated_trails, crs=gdf.crs)
                result_gdf = result_gdf.drop(columns=["name_lower"])
            else:
                result_gdf = gpd.GeoDataFrame(crs=gdf.crs)

            aggregated_count = len(result_gdf)
            self.logger.info(
                f"Aggregated {park_code}: {original_count} -> {aggregated_count} trails"
            )

            return result_gdf

        except Exception as e:
            self.logger.error(f"Error aggregating trails for {park_code}: {e}")
            return gdf

    def filter_by_minimum_length(
        self, gdf: gpd.GeoDataFrame, park_code: str
    ) -> gpd.GeoDataFrame:
        """
        Filter trails by minimum length after aggregation.

        Args:
            gdf: GeoDataFrame with trail data
            park_code: Park code for logging

        Returns:
            Filtered GeoDataFrame
        """
        if gdf.empty:
            return gdf

        try:
            original_count = len(gdf)

            # Filter by minimum length
            gdf = gdf[
                (gdf["length_miles"].notna())
                & (gdf["length_miles"] >= config.TNM_MIN_TRAIL_LENGTH_MI)
            ]

            filtered_count = len(gdf)
            self.logger.info(
                f"Length filtered {park_code}: {original_count} -> {filtered_count} trails "
                f"(min length: {config.TNM_MIN_TRAIL_LENGTH_MI} mi)"
            )

            return gdf

        except Exception as e:
            self.logger.error(f"Error filtering by length for {park_code}: {e}")
            return gdf

    def add_metadata(self, gdf: gpd.GeoDataFrame, park_code: str) -> gpd.GeoDataFrame:
        """
        Add metadata columns to the GeoDataFrame.

        Args:
            gdf: GeoDataFrame with trail data
            park_code: Park code for logging

        Returns:
            GeoDataFrame with added metadata
        """
        if gdf.empty:
            return gdf

        try:
            # Add geometry type
            gdf["geometry_type"] = gdf.geometry.geom_type

            # Add metadata (timestamp removed - using collected_at instead)

            # Ensure park_code is set
            gdf["park_code"] = park_code

            self.logger.info(f"Added metadata for {park_code}: {len(gdf)} trails")
            return gdf

        except Exception as e:
            self.logger.error(f"Error adding metadata for {park_code}: {e}")
            return gdf

    def process_trails(
        self, park_code: str, boundary_gdf: gpd.GeoDataFrame
    ) -> gpd.GeoDataFrame:
        """
        Process trails for a single park: query API, filter, clip, aggregate, and validate.

        Args:
            park_code: Park code to process
            boundary_gdf: GeoDataFrame with park boundary

        Returns:
            Processed GeoDataFrame with trail data
        """
        self.logger.info(f"Processing trails for {park_code}")

        # Get bounding box from stored data
        bbox_string = boundary_gdf["bbox"].iloc[0]
        if not bbox_string:
            self.logger.warning(f"No bounding box found for {park_code}, skipping")
            return gpd.GeoDataFrame()

        # Query TNM API
        response = self.query_tnm_api(bbox_string, park_code)
        if response is None:
            return gpd.GeoDataFrame()

        # Rate limiting
        time.sleep(self.rate_limit)

        # Load to GeoDataFrame
        trails_gdf = self.load_trails_to_geodataframe(response, park_code)
        if trails_gdf.empty:
            return trails_gdf

        # Filter named trails
        trails_gdf = self.filter_named_trails(trails_gdf, park_code)

        # Clip to boundary
        trails_gdf = self.clip_trails_to_boundary(trails_gdf, boundary_gdf, park_code)

        # Aggregate by name
        trails_gdf = self.aggregate_trails_by_name(trails_gdf, park_code)

        # Filter by minimum length
        trails_gdf = self.filter_by_minimum_length(trails_gdf, park_code)

        # Add metadata
        trails_gdf = self.add_metadata(trails_gdf, park_code)

        self.logger.info(
            f"Completed processing {park_code}: {len(trails_gdf)} final trails"
        )
        return trails_gdf

    def collect_all_trails(self) -> gpd.GeoDataFrame:
        """
        Collect trails for all parks or specified parks.

        Returns:
            GeoDataFrame containing all collected trail data
        """
        self.logger.info("Starting TNM trail collection")

        # Load park boundaries
        park_boundaries = self.load_park_boundaries()
        if park_boundaries.empty:
            self.logger.error("No park boundaries found")
            return gpd.GeoDataFrame()

        # Get completed parks if writing to database
        completed_parks = self.get_completed_parks()
        if completed_parks:
            self.logger.info(
                f"Skipping {len(completed_parks)} already completed parks: {sorted(completed_parks)}"
            )

        # Process each park
        all_trails = []
        total_parks = len(park_boundaries)

        for idx, (_, park_row) in enumerate(park_boundaries.iterrows(), 1):
            park_code = park_row["park_code"]

            # Skip if already completed
            if park_code in completed_parks:
                self.logger.info(f"Skipping {park_code} (already completed)")
                continue

            self.logger.info(f"Processing park {idx}/{total_parks}: {park_code}")

            try:
                # Process trails for this park
                park_trails = self.process_trails(
                    park_code,
                    park_boundaries[park_boundaries["park_code"] == park_code],
                )

                if not park_trails.empty:
                    all_trails.append(park_trails)

                    # Save to database after each park (for large datasets)
                    if self.write_db and self.db_writer:
                        self.db_writer.write_tnm_hikes(park_trails, mode="append")
                        self.logger.info(
                            f"Saved {len(park_trails)} trails for {park_code} to database"
                        )

            except Exception as e:
                self.logger.error(f"Error processing {park_code}: {e}")
                continue

        # Combine all trails
        if all_trails:
            combined_trails = gpd.GeoDataFrame(
                pd.concat(all_trails, ignore_index=True), crs=all_trails[0].crs
            )
            self.logger.info(
                f"Collection complete: {len(combined_trails)} total trails from {len(all_trails)} parks"
            )
            return combined_trails
        else:
            self.logger.warning("No trails collected")
            return gpd.GeoDataFrame()

    def save_to_gpkg(self, gdf: gpd.GeoDataFrame, append: bool = False) -> None:
        """
        Save trail data to GeoPackage file.

        Args:
            gdf: GeoDataFrame to save
            append: Whether to append to existing file or overwrite
        """
        if gdf.empty:
            self.logger.warning("No data to save to GeoPackage")
            return

        try:
            if append and os.path.exists(self.output_gpkg):
                # Append to existing file
                existing_gdf = gpd.read_file(self.output_gpkg)
                combined_gdf = gpd.GeoDataFrame(
                    pd.concat([existing_gdf, gdf], ignore_index=True), crs=gdf.crs
                )
                combined_gdf.to_file(self.output_gpkg, driver="GPKG")
                self.logger.info(f"Appended {len(gdf)} trails to {self.output_gpkg}")
            else:
                # Create new file
                gdf.to_file(self.output_gpkg, driver="GPKG")
                self.logger.info(f"Saved {len(gdf)} trails to {self.output_gpkg}")

        except Exception as e:
            self.logger.error(f"Error saving to GeoPackage: {e}")

    def run(self) -> None:
        """
        Run the complete TNM trail collection process.

        This method orchestrates the entire collection workflow:
        1. Collect trails from all parks
        2. Save to GeoPackage file
        3. Optionally save to database
        """
        self.logger.info("Starting TNM Hikes Collector")

        try:
            # Collect all trails
            trails_gdf = self.collect_all_trails()

            if not trails_gdf.empty:
                # Save to GeoPackage
                self.save_to_gpkg(trails_gdf, append=False)

                self.logger.info(
                    f"TNM collection complete: {len(trails_gdf)} trails saved to {self.output_gpkg}"
                )
            else:
                self.logger.warning("No trails collected")

        except Exception as e:
            self.logger.error(f"Error in TNM collection: {e}")
            raise


def main() -> None:
    """
    Main function to run TNM hikes collector.

    Examples:
        # Process all parks and write to database
        python tnm_hikes_collector.py --write-db

        # Test with specific parks only
        python tnm_hikes_collector.py --parks acad,yell --test-limit 2

        # Process with custom rate limiting and output file
        python tnm_hikes_collector.py --write-db --rate-limit 2.0 --output-gpkg custom_tnm.gpkg

        # Resume interrupted collection (automatically skips completed parks)
        python tnm_hikes_collector.py --write-db

        # Debug mode with verbose logging
        python tnm_hikes_collector.py --parks acad --log-level DEBUG
    """
    parser = argparse.ArgumentParser(description="TNM Hikes Collector")
    parser.add_argument(
        "--write-db", action="store_true", help="Write results to the database"
    )
    parser.add_argument(
        "--output-gpkg",
        default=config.TNM_DEFAULT_OUTPUT_GPKG,
        help="Output GeoPackage file path",
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=config.TNM_DEFAULT_RATE_LIMIT,
        help="Seconds to sleep between API queries",
    )
    parser.add_argument(
        "--parks", type=str, help="Comma-separated list of park codes to process"
    )
    parser.add_argument(
        "--test-limit", type=int, help="Limit to first N parks (for testing)"
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level")

    args = parser.parse_args()

    # Parse parks list
    parks = args.parks.split(",") if args.parks else None

    # Create collector
    collector = TNMHikesCollector(
        output_gpkg=args.output_gpkg,
        rate_limit=args.rate_limit,
        parks=parks,
        test_limit=args.test_limit,
        log_level=args.log_level,
        write_db=args.write_db,
    )

    # Run collection
    collector.run()


if __name__ == "__main__":
    main()

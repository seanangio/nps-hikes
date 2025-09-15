#!/usr/bin/env python3
"""
USGS Elevation Data Collector

Fetches elevation data for matched trails using USGS free API.
Only collects data - no analysis or visualization.
"""

import requests
import time
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, LineString
from sqlalchemy import text
import json
import os
from typing import List, Dict, Tuple, Optional
import argparse

# Add project root to path for imports
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.settings import config
from db_writer import get_postgres_engine, DatabaseWriter
from profiling.utils import ProfilingLogger

logger = ProfilingLogger("usgs_elevation_collector")


class USGSElevationCollector:
    """Collect elevation data for matched trails using USGS API."""

    def __init__(self):
        """Initialize the collector."""
        self.engine = get_postgres_engine()
        self.db_writer = DatabaseWriter(self.engine, logger)
        self.elevation_cache = {}

        # USGS API settings
        self.usgs_api_base = "https://epqs.nationalmap.gov/v1/json"
        self.sample_distance_m = 50  # Sample every 50 meters
        self.api_timeout = 10  # 10 second timeout
        self.rate_limit_delay = 1  # 1 second delay between requests
        self.error_threshold = 0.1  # 10% failure rate threshold

        # Cache file for persistence
        self.cache_file = "cache/elevation_cache.json"
        self._load_cache()

    def _load_cache(self):
        """Load elevation cache from disk."""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, "r") as f:
                    self.elevation_cache = json.load(f)
                logger.info(
                    f"Loaded {len(self.elevation_cache)} cached elevation points"
                )
        except Exception as e:
            logger.error(f"Failed to load elevation cache: {e}")
            self.elevation_cache = {}

    def _save_cache(self):
        """Save elevation cache to disk."""
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, "w") as f:
                json.dump(self.elevation_cache, f)
            logger.info(f"Saved {len(self.elevation_cache)} elevation points to cache")
        except Exception as e:
            logger.error(f"Failed to save elevation cache: {e}")

    def get_elevation_usgs(self, lat: float, lon: float) -> Optional[float]:
        """Get elevation from USGS free API with caching and rate limiting."""
        # Check cache first
        cache_key = f"{lat:.6f},{lon:.6f}"
        if cache_key in self.elevation_cache:
            return self.elevation_cache[cache_key]

        # Rate limiting
        time.sleep(self.rate_limit_delay)

        try:
            url = f"{self.usgs_api_base}?x={lon}&y={lat}&units=Meters&includeDate=false"
            response = requests.get(url, timeout=self.api_timeout)

            if response.status_code == 200:
                data = response.json()
                if "value" in data:
                    elevation = data["value"]
                    elevation_float = float(elevation)

                    # Cache the result
                    self.elevation_cache[cache_key] = elevation_float
                    return elevation_float

            logger.error(
                f"Failed to get elevation for ({lat:.6f}, {lon:.6f}): {response.status_code}"
            )
            return None

        except Exception as e:
            logger.error(f"Error getting elevation from USGS API: {e}")
            return None

    def sample_trail_elevation(
        self, trail_geometry: LineString
    ) -> Tuple[List[Dict], str]:
        """
        Sample elevation along trail at regular intervals.

        Args:
            trail_geometry: Trail LineString geometry

        Returns:
            Tuple of (elevation_data_list, collection_status)
        """
        # Convert sample distance from meters to degrees (rough approximation)
        sample_distance_deg = self.sample_distance_m / 111000

        # Extract points along the line at regular intervals
        points = []
        total_length = trail_geometry.length

        # Sample at regular intervals
        for distance in np.arange(0, total_length, sample_distance_deg):
            point = trail_geometry.interpolate(distance)
            points.append((distance, point.y, point.x))  # (distance_deg, lat, lon)

        # Add the end point
        end_point = trail_geometry.interpolate(total_length)
        points.append((total_length, end_point.y, end_point.x))

        # Get elevation for each point
        elevation_data = []
        failed_count = 0
        cumulative_distance = 0.0

        for i, (distance_deg, lat, lon) in enumerate(points):
            elevation = self.get_elevation_usgs(lat, lon)

            if elevation is not None:
                # Calculate cumulative distance in meters
                if i > 0:
                    prev_distance_deg = points[i - 1][0]
                    distance_increment = (distance_deg - prev_distance_deg) * 111000
                    cumulative_distance += distance_increment

                elevation_data.append(
                    {
                        "point_index": i,
                        "distance_m": cumulative_distance,
                        "latitude": lat,
                        "longitude": lon,
                        "elevation_m": elevation,
                    }
                )
            else:
                failed_count += 1
                logger.error(
                    f"Failed to get elevation for point {i} ({lat:.6f}, {lon:.6f})"
                )

        # Determine collection status
        total_points = len(points)
        failure_rate = failed_count / total_points if total_points > 0 else 1.0

        if failure_rate > self.error_threshold:
            collection_status = "FAILED"
            logger.error(
                f"High failure rate: {failure_rate:.1%} ({failed_count}/{total_points})"
            )
        elif failed_count > 0:
            collection_status = "PARTIAL"
            logger.error(
                f"Partial collection: {failure_rate:.1%} failed ({failed_count}/{total_points})"
            )
        else:
            collection_status = "COMPLETE"
            logger.info(f"Complete collection: {total_points} points")

        return elevation_data, collection_status

    def create_elevation_table(self):
        """Create the usgs_trail_elevations table using db_writer."""
        self.db_writer.ensure_table_exists("usgs_trail_elevations")

    def collect_park_elevation_data(
        self, park_code: str, force_refresh: bool = False
    ) -> Dict:
        """
        Collect elevation data for all matched trails in a park.

        Args:
            park_code: Park code to process
            force_refresh: If True, re-collect data even if already exists

        Returns:
            Dictionary with collection results
        """
        logger.info(f"Collecting elevation data for park: {park_code}")

        # Query matched trails for this park
        query = f"""
            SELECT id, matched_trail_name, matched_trail_geometry, source
            FROM gmaps_hiking_locations_matched
            WHERE park_code = '{park_code}' 
            AND match_status = 'MATCHED'
            AND matched_trail_geometry IS NOT NULL
            ORDER BY matched_trail_name
        """

        trails_df = gpd.read_postgis(
            query, self.engine, geom_col="matched_trail_geometry"
        )

        if trails_df.empty:
            logger.error(f"No matched trails found for park: {park_code}")
            return {
                "processed_count": 0,
                "failed_count": 0,
                "partial_count": 0,
                "complete_count": 0,
            }

        # Check for existing elevation data (unless force_refresh)
        existing_trail_ids = set()
        if not force_refresh:
            existing_query = f"""
                SELECT trail_id FROM usgs_trail_elevations 
                WHERE park_code = '{park_code}'
            """
            try:
                with self.engine.connect() as conn:
                    result = conn.execute(text(existing_query))
                    existing_trail_ids = {row[0] for row in result.fetchall()}
                logger.info(
                    f"Found {len(existing_trail_ids)} trails with existing elevation data"
                )
            except Exception as e:
                logger.error(f"Failed to check existing elevation data: {e}")

        # Process each trail
        processed_count = 0
        failed_count = 0
        partial_count = 0
        complete_count = 0

        for _, trail in trails_df.iterrows():
            trail_id = trail["id"]
            trail_name = trail["matched_trail_name"]
            trail_geometry = trail["matched_trail_geometry"]
            source = trail["source"]

            logger.info(f"Processing trail: {trail_name}")

            # Skip if already collected (unless force_refresh)
            if not force_refresh and trail_id in existing_trail_ids:
                logger.info(f"Skipping {trail_name} - elevation data already exists")
                continue

            # Check if geometry is valid
            if not trail_geometry.is_valid:
                logger.error(f"Invalid geometry for trail: {trail_name}")
                failed_count += 1
                continue

            # Get elevation data
            elevation_data, collection_status = self.sample_trail_elevation(
                trail_geometry
            )

            if collection_status == "FAILED":
                logger.error(f"Failed to collect elevation data for: {trail_name}")
                failed_count += 1
                continue

            # Count status
            if collection_status == "PARTIAL":
                partial_count += 1
            elif collection_status == "COMPLETE":
                complete_count += 1

            # Calculate failed points count
            total_points = len(elevation_data) if elevation_data else 0
            failed_points = 0  # We filtered out failed points, so this is 0

            # Store in database (UPSERT to handle re-runs)
            insert_sql = """
                INSERT INTO usgs_trail_elevations 
                (trail_id, trail_name, park_code, source, elevation_points, 
                 collection_status, failed_points_count, total_points_count)
                VALUES (:trail_id, :trail_name, :park_code, :source, :elevation_points,
                        :collection_status, :failed_points_count, :total_points_count)
                ON CONFLICT (trail_id) DO UPDATE SET
                    elevation_points = EXCLUDED.elevation_points,
                    collection_status = EXCLUDED.collection_status,
                    failed_points_count = EXCLUDED.failed_points_count,
                    total_points_count = EXCLUDED.total_points_count,
                    created_at = NOW()
            """

            try:
                with self.engine.connect() as conn:
                    conn.execute(
                        text(insert_sql),
                        {
                            "trail_id": trail_id,
                            "trail_name": trail_name,
                            "park_code": park_code,
                            "source": source,
                            "elevation_points": json.dumps(elevation_data),
                            "collection_status": collection_status,
                            "failed_points_count": failed_points,
                            "total_points_count": total_points,
                        },
                    )
                    conn.commit()

                processed_count += 1
                logger.info(
                    f"Stored elevation data for: {trail_name} ({collection_status})"
                )

            except Exception as e:
                logger.error(f"Failed to store elevation data for {trail_name}: {e}")
                failed_count += 1

        # Save cache
        self._save_cache()

        results = {
            "processed_count": processed_count,
            "failed_count": failed_count,
            "partial_count": partial_count,
            "complete_count": complete_count,
        }

        logger.info(f"Collection complete for {park_code}: {results}")
        return results

    def collect_all_parks_elevation_data(
        self,
        parks: Optional[List[str]] = None,
        test_limit: Optional[int] = None,
        force_refresh: bool = False,
    ) -> Dict:
        """
        Collect elevation data for all parks with matched trails.

        Args:
            parks: Optional list of specific park codes to process
            test_limit: Optional limit on number of parks to process (for testing)
            force_refresh: If True, re-collect data even if already exists

        Returns:
            Dictionary with collection results
        """
        logger.info("Starting elevation data collection for all parks")

        # Get list of parks with matched trails
        if parks:
            parks_str = "', '".join(parks)
            query = f"""
                SELECT DISTINCT park_code 
                FROM gmaps_hiking_locations_matched 
                WHERE park_code IN ('{parks_str}')
                AND match_status = 'MATCHED'
                ORDER BY park_code
            """
        else:
            query = """
                SELECT DISTINCT park_code 
                FROM gmaps_hiking_locations_matched 
                WHERE match_status = 'MATCHED'
                ORDER BY park_code
            """

        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                available_parks = [row[0] for row in result.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get list of parks: {e}")
            return {
                "total_parks": 0,
                "total_processed": 0,
                "total_complete": 0,
                "total_partial": 0,
                "total_failed": 0,
            }

        if not available_parks:
            logger.error("No parks with matched trails found")
            return {
                "total_parks": 0,
                "total_processed": 0,
                "total_complete": 0,
                "total_partial": 0,
                "total_failed": 0,
            }

        # Apply test limit if specified
        if test_limit:
            available_parks = available_parks[:test_limit]
            logger.info(f"Limited to first {test_limit} parks for testing")

        logger.info(
            f"Found {len(available_parks)} parks with matched trails: {', '.join(available_parks)}"
        )

        # Process each park
        total_parks = len(available_parks)
        total_processed = 0
        total_complete = 0
        total_partial = 0
        total_failed = 0

        for i, park_code in enumerate(available_parks, 1):
            logger.info(f"Processing park {i}/{total_parks}: {park_code}")

            try:
                results = self.collect_park_elevation_data(park_code, force_refresh)
                total_processed += results["processed_count"]
                total_complete += results["complete_count"]
                total_partial += results["partial_count"]
                total_failed += results["failed_count"]
            except Exception as e:
                logger.error(f"Failed to process park {park_code}: {e}")
                continue

        # Final summary
        final_results = {
            "total_parks": total_parks,
            "total_processed": total_processed,
            "total_complete": total_complete,
            "total_partial": total_partial,
            "total_failed": total_failed,
        }

        logger.info(f"Collection complete for all parks: {final_results}")
        return final_results


def main():
    """Main function for elevation data collection."""
    parser = argparse.ArgumentParser(
        description="Collect USGS elevation data for trails"
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
        "--create-table", action="store_true", help="Create elevation database table"
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Re-collect data even if already exists",
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level")

    args = parser.parse_args()

    # Initialize collector
    collector = USGSElevationCollector()

    if args.create_table:
        collector.create_elevation_table()

    # Parse parks list
    parks = args.parks.split(",") if args.parks else None

    # Collect elevation data for all parks or specified parks
    results = collector.collect_all_parks_elevation_data(
        parks=parks, test_limit=args.test_limit, force_refresh=args.force_refresh
    )

    print(f"\nUSGS Elevation Data Collection Results:")
    print(f"Total Parks Processed: {results['total_parks']}")
    print(f"Total Trails Processed: {results['total_processed']}")
    print(f"Total Complete: {results['total_complete']}")
    print(f"Total Partial: {results['total_partial']}")
    print(f"Total Failed: {results['total_failed']}")


if __name__ == "__main__":
    main()

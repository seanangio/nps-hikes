#!/usr/bin/env python3
"""
Trail Matching System

This module matches GMaps hiking location points to trail linestrings from OSM and TNM data.
It uses fuzzy name matching combined with geographic distance validation to find the best matches.

The output is a denormalized view for analytical convenience that includes:
- Original GMaps data (id, park_code, location_name, latitude, longitude, created_at)
- Matched trail information (name, geometry, source)
- Matching metrics (confidence scores, distances)

Usage:
    python trail_matcher.py
"""

import argparse
import logging
import math
import os
import sys
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import pandas as pd
import geopandas as gpd
from sqlalchemy import text
from shapely.geometry import Point
from shapely.ops import nearest_points
import difflib

# Add project root to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.settings import config
from db_writer import get_postgres_engine, DatabaseWriter
from utils.logging import setup_logging


class TrailMatcher:
    """Match GMaps hiking locations to trail linestrings."""

    def __init__(
        self,
        write_db: bool = False,
        test_limit: Optional[int] = None,
        logger: logging.Logger = None,
    ):
        """
        Initialize the trail matcher.

        Args:
            write_db (bool): Whether to write results to the database
            test_limit (Optional[int]): Limit processing to first N parks for testing
            logger (logging.Logger): Logger instance for operation tracking
        """
        self.logger = logger or logging.getLogger("trail_matcher")
        self.engine = get_postgres_engine()
        self.db_writer = DatabaseWriter(self.engine, self.logger) if write_db else None
        self.test_limit = test_limit

        # Matching parameters from config
        self.distance_threshold_m = config.TRAIL_MATCHING_DISTANCE_THRESHOLD_M
        self.confidence_threshold = config.TRAIL_MATCHING_CONFIDENCE_THRESHOLD
        self.name_weight = config.TRAIL_MATCHING_NAME_WEIGHT
        self.distance_weight = config.TRAIL_MATCHING_DISTANCE_WEIGHT

        # Statistics for profiling
        self.stats = {
            "total_gmaps_points": 0,
            "matched_tnm": 0,
            "matched_osm": 0,
            "no_match": 0,
            "avg_confidence_score": 0,
            "avg_distance_m": 0,
            "processing_time": 0,
        }

    def preprocess_name(self, name: str) -> str:
        """
        Preprocess trail name for matching.

        Args:
            name: Original trail name

        Returns:
            Preprocessed name
        """
        if not name:
            return ""

        # Convert to lowercase and strip whitespace
        processed = name.lower().strip()

        # Remove common meaningless words
        words_to_remove = [
            "trail",
            "trailhead",
            "trails",
            "path",
            "paths",
            "walk",
            "walks",
        ]
        for word in words_to_remove:
            processed = processed.replace(word, "")

        # Remove extra whitespace and punctuation
        processed = " ".join(processed.split())
        processed = processed.replace(",", "").replace(".", "").replace("-", " ")

        return processed.strip()

    def calculate_name_similarity(self, name1: str, name2: str) -> float:
        """
        Calculate similarity between two trail names.

        Args:
            name1: First name
            name2: Second name

        Returns:
            Similarity score between 0 and 1
        """
        if not name1 or not name2:
            return 0.0

        processed1 = self.preprocess_name(name1)
        processed2 = self.preprocess_name(name2)

        if not processed1 or not processed2:
            return 0.0

        # Use difflib for fuzzy matching
        similarity = difflib.SequenceMatcher(None, processed1, processed2).ratio()

        # Boost score for partial matches (one name contains the other)
        if processed1 in processed2 or processed2 in processed1:
            similarity = max(similarity, 0.8)

        return similarity

    def calculate_distance_to_trail(self, point: Point, trail_geometry) -> float:
        """
        Calculate minimum distance from point to trail geometry.

        Args:
            point: Shapely Point
            trail_geometry: Shapely LineString

        Returns:
            Distance in meters
        """
        try:
            # Use the built-in distance method which is more reliable
            distance_deg = point.distance(trail_geometry)

            # Convert to meters using a more accurate approximation
            # At the latitude of most US parks (~30-50 degrees), 1 degree ≈ 111,000m
            # But we can be more precise by using the latitude
            lat = point.y
            meters_per_degree_lat = 111000  # Constant
            meters_per_degree_lon = 111000 * abs(math.cos(math.radians(lat)))

            # For small distances, we can approximate the distance in meters
            # by using the Euclidean distance in degrees scaled by the average meters per degree
            avg_meters_per_degree = (meters_per_degree_lat + meters_per_degree_lon) / 2
            distance_m = distance_deg * avg_meters_per_degree

            return distance_m
        except Exception as e:
            self.logger.warning(f"Error calculating distance: {e}")
            # Fallback to simple approximation
            try:
                distance_deg = point.distance(trail_geometry)
                distance_m = distance_deg * 111000
                return distance_m
            except:
                return float("inf")

    def calculate_confidence_score(
        self, name_similarity: float, distance_m: float
    ) -> float:
        """
        Calculate combined confidence score.

        Args:
            name_similarity: Name similarity score (0-1)
            distance_m: Distance in meters

        Returns:
            Combined confidence score (0-1)
        """
        # Distance score: closer is better, capped at threshold
        distance_score = max(0, 1 - (distance_m / self.distance_threshold_m))

        # Combined score
        confidence = (name_similarity * self.name_weight) + (
            distance_score * self.distance_weight
        )

        return min(1.0, confidence)

    def find_tnm_matches(self, gmaps_point: Dict) -> List[Dict]:
        """
        Find potential TNM trail matches for a GMaps point.

        Args:
            gmaps_point: GMaps point dictionary

        Returns:
            List of potential matches with scores
        """
        park_code = gmaps_point["park_code"]
        location_name = gmaps_point["location_name"]
        point_geom = Point(gmaps_point["longitude"], gmaps_point["latitude"])

        # Query TNM trails for this park
        query = f"""
        SELECT name, lengthmiles as length_mi, geometry
        FROM tnm_hikes 
        WHERE park_code = '{park_code}'
        """

        try:
            tnm_trails = gpd.read_postgis(query, self.engine, geom_col="geometry")
        except Exception as e:
            self.logger.error(f"Error querying TNM trails for {park_code}: {e}")
            return []

        matches = []

        for _, trail in tnm_trails.iterrows():
            trail_name = trail["name"] or "Unnamed"

            # Calculate name similarity
            name_similarity = self.calculate_name_similarity(location_name, trail_name)

            # Calculate distance
            distance_m = self.calculate_distance_to_trail(point_geom, trail["geometry"])

            # Skip if too far
            if distance_m > self.distance_threshold_m:
                continue

            # Calculate confidence score
            confidence = self.calculate_confidence_score(name_similarity, distance_m)

            matches.append(
                {
                    "trail_name": trail_name,
                    "trail_geometry": trail["geometry"],
                    "source": "TNM",
                    "name_similarity_score": name_similarity,
                    "min_point_to_trail_distance_m": distance_m,
                    "confidence_score": confidence,
                }
            )

        return matches

    def find_osm_matches(self, gmaps_point: Dict) -> List[Dict]:
        """
        Find potential OSM trail matches for a GMaps point.

        Args:
            gmaps_point: GMaps point dictionary

        Returns:
            List of potential matches with scores
        """
        park_code = gmaps_point["park_code"]
        location_name = gmaps_point["location_name"]
        point_geom = Point(gmaps_point["longitude"], gmaps_point["latitude"])

        # Query OSM trails for this park
        query = f"""
        SELECT name, length_mi, geometry
        FROM osm_hikes 
        WHERE park_code = '{park_code}'
        """

        try:
            osm_trails = gpd.read_postgis(query, self.engine, geom_col="geometry")
        except Exception as e:
            self.logger.error(f"Error querying OSM trails for {park_code}: {e}")
            return []

        matches = []

        for _, trail in osm_trails.iterrows():
            trail_name = trail["name"] or "Unnamed"

            # Calculate name similarity
            name_similarity = self.calculate_name_similarity(location_name, trail_name)

            # Calculate distance
            distance_m = self.calculate_distance_to_trail(point_geom, trail["geometry"])

            # Skip if too far
            if distance_m > self.distance_threshold_m:
                continue

            # Calculate confidence score
            confidence = self.calculate_confidence_score(name_similarity, distance_m)

            matches.append(
                {
                    "trail_name": trail_name,
                    "trail_geometry": trail["geometry"],
                    "source": "OSM",
                    "name_similarity_score": name_similarity,
                    "min_point_to_trail_distance_m": distance_m,
                    "confidence_score": confidence,
                }
            )

        return matches

    def match_gmaps_point(self, gmaps_point: Dict) -> Dict:
        """
        Find the best match for a single GMaps point.

        Args:
            gmaps_point: GMaps point dictionary

        Returns:
            Match result dictionary
        """
        # Try TNM first
        tnm_matches = self.find_tnm_matches(gmaps_point)

        if tnm_matches:
            # Find best TNM match
            best_match = max(tnm_matches, key=lambda x: x["confidence_score"])

            if best_match["confidence_score"] >= self.confidence_threshold:
                self.stats["matched_tnm"] += 1
                return {
                    **gmaps_point,
                    "matched_trail_name": best_match["trail_name"],
                    "source": best_match["source"],
                    "name_similarity_score": best_match["name_similarity_score"],
                    "min_point_to_trail_distance_m": best_match[
                        "min_point_to_trail_distance_m"
                    ],
                    "confidence_score": best_match["confidence_score"],
                    "match_status": "MATCHED",
                    "matched_trail_geometry": best_match["trail_geometry"],
                }

        # Try OSM if no good TNM match
        osm_matches = self.find_osm_matches(gmaps_point)

        if osm_matches:
            # Find best OSM match
            best_match = max(osm_matches, key=lambda x: x["confidence_score"])

            if best_match["confidence_score"] >= self.confidence_threshold:
                self.stats["matched_osm"] += 1
                return {
                    **gmaps_point,
                    "matched_trail_name": best_match["trail_name"],
                    "source": best_match["source"],
                    "name_similarity_score": best_match["name_similarity_score"],
                    "min_point_to_trail_distance_m": best_match[
                        "min_point_to_trail_distance_m"
                    ],
                    "confidence_score": best_match["confidence_score"],
                    "match_status": "MATCHED",
                    "matched_trail_geometry": best_match["trail_geometry"],
                }

        # No match found
        self.stats["no_match"] += 1
        return {
            **gmaps_point,
            "matched_trail_name": None,
            "source": None,
            "name_similarity_score": None,
            "min_point_to_trail_distance_m": None,
            "confidence_score": None,
            "match_status": "NO_MATCH",
            "matched_trail_geometry": None,
        }

    def create_matched_table(self, matched_data: List[Dict]) -> None:
        """
        Create the gmaps_hiking_locations_matched table using DatabaseWriter.

        Args:
            matched_data: List of matched records
        """
        self.logger.info("Creating gmaps_hiking_locations_matched table...")

        # Convert to DataFrame
        df = pd.DataFrame(matched_data)

        # Convert to GeoDataFrame, specifying geometry column
        gdf = gpd.GeoDataFrame(df, geometry="matched_trail_geometry", crs="EPSG:4326")

        # Reorder columns
        column_order = [
            "id",
            "park_code",
            "location_name",
            "latitude",
            "longitude",
            "created_at",
            "matched_trail_name",
            "source",
            "name_similarity_score",
            "min_point_to_trail_distance_m",
            "confidence_score",
            "match_status",
            "matched_trail_geometry",
        ]
        gdf = gdf[column_order]

        # Write to database using DatabaseWriter
        if self.db_writer:
            self.db_writer.write_gmaps_hiking_locations_matched(gdf, mode="replace")
        else:
            # Fallback to file output
            output_path = config.TRAIL_MATCHING_OUTPUT_GPKG
            gdf.to_file(output_path, driver="GPKG")
            self.logger.info(
                f"Saved matched data to {output_path} with {len(gdf)} records"
            )

        self.logger.info(f"Created table with {len(gdf)} records")

    def run_matching(self) -> None:
        """Run the complete trail matching process."""
        start_time = datetime.now()
        self.logger.info("Starting trail matching process...")

        try:
            # Get all GMaps points
            query = """
            SELECT id, park_code, location_name, latitude, longitude, created_at
            FROM gmaps_hiking_locations
            ORDER BY id
            """

            gmaps_points = pd.read_sql(query, self.engine)

            # Apply test limit if specified
            if self.test_limit is not None:
                gmaps_points = gmaps_points.head(self.test_limit)
                self.logger.info(
                    f"TESTING MODE: Limited to first {self.test_limit} GMaps points"
                )

            self.stats["total_gmaps_points"] = len(gmaps_points)

            self.logger.info(f"Processing {len(gmaps_points)} GMaps points...")

            # Process each point
            matched_data = []
            confidence_scores = []
            distances = []

            for _, point in gmaps_points.iterrows():
                match_result = self.match_gmaps_point(point.to_dict())
                matched_data.append(match_result)

                # Collect stats
                if match_result["confidence_score"] is not None:
                    confidence_scores.append(match_result["confidence_score"])
                if match_result["min_point_to_trail_distance_m"] is not None:
                    distances.append(match_result["min_point_to_trail_distance_m"])

                if len(matched_data) % 20 == 0:
                    self.logger.info(
                        f"Processed {len(matched_data)}/{len(gmaps_points)} points..."
                    )

            # Calculate final stats
            self.stats["avg_confidence_score"] = (
                sum(confidence_scores) / len(confidence_scores)
                if confidence_scores
                else 0
            )
            self.stats["avg_distance_m"] = (
                sum(distances) / len(distances) if distances else 0
            )
            self.stats["processing_time"] = (
                datetime.now() - start_time
            ).total_seconds()

            # Create output table
            self.create_matched_table(matched_data)

            # Print summary
            self._print_summary()

        except Exception as e:
            self.logger.error(f"Matching process failed: {e}")
            raise

    def _print_summary(self) -> None:
        """Print matching summary."""
        self.logger.info("=" * 60)
        self.logger.info("TRAIL MATCHING SUMMARY")
        self.logger.info("=" * 60)
        self.logger.info(
            f"Total GMaps points processed: {self.stats['total_gmaps_points']}"
        )
        self.logger.info(f"Successfully matched (TNM): {self.stats['matched_tnm']}")
        self.logger.info(f"Successfully matched (OSM): {self.stats['matched_osm']}")
        self.logger.info(f"No match found: {self.stats['no_match']}")
        self.logger.info(
            f"Match rate: {((self.stats['matched_tnm'] + self.stats['matched_osm']) / self.stats['total_gmaps_points'] * 100):.1f}%"
        )
        self.logger.info(
            f"Average confidence score: {self.stats['avg_confidence_score']:.3f}"
        )
        self.logger.info(
            f"Average distance to trail: {self.stats['avg_distance_m']:.1f}m"
        )
        self.logger.info(
            f"Processing time: {self.stats['processing_time']:.2f} seconds"
        )
        self.logger.info("=" * 60)


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Match GMaps hiking locations to trail linestrings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # Process all GMaps points, write to database
  %(prog)s --file-only                  # Write results to file only
  %(prog)s --test-limit 10              # Test with first 10 GMaps points only
  %(prog)s --file-only --test-limit 5   # Test mode with file output
  %(prog)s --log-level DEBUG            # Enable debug logging
        """,
    )
    parser.add_argument(
        "--file-only",
        action="store_true",
        help="Write results to file only (default: write to database)",
    )
    parser.add_argument(
        "--test-limit",
        type=int,
        help="Limit to first N GMaps points (for testing)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Set logging level",
    )

    args = parser.parse_args()

    # Set up centralized logging
    logger = setup_logging(
        log_level=args.log_level,
        log_file="logs/trail_matcher.log",
        logger_name="trail_matcher",
    )

    try:
        # Initialize matcher with new parameters
        # Default to database writing (original behavior), use file-only if specified
        matcher = TrailMatcher(
            write_db=not args.file_only, test_limit=args.test_limit, logger=logger
        )

        # Run matching
        matcher.run_matching()

        logger.info("Trail matching completed successfully")

    except Exception as e:
        logger.error(f"Trail matching failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

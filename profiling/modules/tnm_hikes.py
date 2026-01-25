"""
TNM Hikes Profiling Module

This module provides comprehensive analysis and profiling capabilities for TNM hiking trail data.
It includes statistical analysis, data quality assessment, and comparison metrics for trail
collections from The National Map.

Key Features:
- Trail count and length statistics by park
- Data quality analysis (completeness, consistency)
- Trail type and designation breakdowns
- Spatial distribution analysis
- Comparison metrics between different collection runs
- Export capabilities for analysis results

The module integrates with the existing profiling framework and provides both
programmatic and command-line interfaces for analysis.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import geopandas as gpd
import pandas as pd
from sqlalchemy import Engine, text

# Add project root to path for imports
project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

# Load environment variables
from dotenv import load_dotenv

load_dotenv(
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
)

from config.settings import config
from scripts.database.db_writer import get_postgres_engine
from utils.logging import setup_tnm_collector_logging


class TNMHikesProfiler:
    """
    A class for profiling and analyzing TNM hiking trail data.

    This class provides comprehensive analysis capabilities for TNM trail data,
    including statistical summaries, data quality assessment, and comparison
    metrics between different data sources or collection runs.
    """

    def __init__(self, log_level: str = "INFO"):
        """
        Initialize the TNM hikes profiler.

        Args:
            log_level (str): Logging level for the profiler
        """
        self.logger = setup_tnm_collector_logging(log_level)
        self.engine = get_postgres_engine()

        self.logger.info("TNM Hikes Profiler initialized")

    def get_trail_statistics(
        self, park_codes: list[str] | None = None
    ) -> Dict[str, Any]:
        """
        Get comprehensive trail statistics for specified parks or all parks.

        Args:
            park_codes (list[str] | None): List of park codes to analyze.
                                            If None, analyzes all parks.

        Returns:
            Dict containing trail statistics including counts, lengths, and breakdowns
        """
        self.logger.info("Generating trail statistics")

        # Build SQL query
        if park_codes:
            park_codes_str = ",".join([f"'{code}'" for code in park_codes])
            park_filter = f"WHERE park_code IN ({park_codes_str})"
        else:
            park_filter = ""

        sql = f"""
        SELECT
            park_code,
            COUNT(*) as trail_count,
            COUNT(CASE WHEN name IS NOT NULL AND name != '' THEN 1 END) as named_trail_count,
            COUNT(CASE WHEN name IS NULL OR name = '' THEN 1 END) as unnamed_trail_count,
            AVG(lengthmiles) as avg_length_miles,
            MIN(lengthmiles) as min_length_miles,
            MAX(lengthmiles) as max_length_miles,
            SUM(lengthmiles) as total_length_miles,
            COUNT(CASE WHEN hikerpedestrian = 'Y' THEN 1 END) as hiker_pedestrian_count,
            COUNT(CASE WHEN hikerpedestrian = 'N' THEN 1 END) as non_hiker_pedestrian_count,
            COUNT(CASE WHEN hikerpedestrian IS NULL THEN 1 END) as unknown_hiker_pedestrian_count,
            COUNT(CASE WHEN trailtype IS NOT NULL THEN 1 END) as typed_trail_count,
            COUNT(CASE WHEN nationaltraildesignation IS NOT NULL THEN 1 END) as designated_trail_count
        FROM tnm_hikes
        {park_filter}
        GROUP BY park_code
        ORDER BY trail_count DESC
        """

        try:
            df = pd.read_sql(sql, self.engine)

            # Calculate additional statistics
            stats = {
                "park_statistics": df.to_dict("records"),
                "summary": {
                    "total_parks": len(df),
                    "total_trails": df["trail_count"].sum(),
                    "total_length_miles": df["total_length_miles"].sum(),
                    "avg_trails_per_park": df["trail_count"].mean(),
                    "avg_length_per_trail": df["avg_length_miles"].mean(),
                    "parks_with_trails": len(df[df["trail_count"] > 0]),
                },
            }

            self.logger.info(f"Generated statistics for {len(df)} parks")
            return stats

        except Exception as e:
            self.logger.error(f"Error generating trail statistics: {e}")
            return {}

    def get_trail_type_breakdown(
        self, park_codes: list[str] | None = None
    ) -> Dict[str, Any]:
        """
        Get breakdown of trails by type and designation.

        Args:
            park_codes (list[str] | None): List of park codes to analyze.
                                            If None, analyzes all parks.

        Returns:
            Dict containing trail type and designation breakdowns
        """
        self.logger.info("Generating trail type breakdown")

        # Build SQL query
        if park_codes:
            park_codes_str = ",".join([f"'{code}'" for code in park_codes])
            park_filter = f"WHERE park_code IN ({park_codes_str})"
        else:
            park_filter = ""

        # Trail type breakdown
        type_sql = f"""
        SELECT
            trailtype,
            COUNT(*) as count,
            AVG(lengthmiles) as avg_length_miles,
            SUM(lengthmiles) as total_length_miles
        FROM tnm_hikes
        {park_filter}
        GROUP BY trailtype
        ORDER BY count DESC
        """

        # National designation breakdown
        designation_sql = f"""
        SELECT
            nationaltraildesignation,
            COUNT(*) as count,
            AVG(lengthmiles) as avg_length_miles,
            SUM(lengthmiles) as total_length_miles
        FROM tnm_hikes
        {park_filter}
        GROUP BY nationaltraildesignation
        ORDER BY count DESC
        """

        try:
            type_df = pd.read_sql(type_sql, self.engine)
            designation_df = pd.read_sql(designation_sql, self.engine)

            breakdown = {
                "trail_types": type_df.to_dict("records"),
                "national_designations": designation_df.to_dict("records"),
                "summary": {
                    "unique_trail_types": len(type_df),
                    "unique_designations": len(designation_df),
                    "most_common_type": (
                        type_df.iloc[0]["trailtype"] if len(type_df) > 0 else None
                    ),
                    "most_common_designation": (
                        designation_df.iloc[0]["nationaltraildesignation"]
                        if len(designation_df) > 0
                        else None
                    ),
                },
            }

            self.logger.info(
                f"Generated type breakdown: {len(type_df)} types, {len(designation_df)} designations"
            )
            return breakdown

        except Exception as e:
            self.logger.error(f"Error generating trail type breakdown: {e}")
            return {}

    def get_data_quality_metrics(
        self, park_codes: list[str] | None = None
    ) -> Dict[str, Any]:
        """
        Assess data quality and completeness for TNM trail data.

        Args:
            park_codes (list[str] | None): List of park codes to analyze.
                                            If None, analyzes all parks.

        Returns:
            Dict containing data quality metrics
        """
        self.logger.info("Assessing data quality")

        # Build SQL query
        if park_codes:
            park_codes_str = ",".join([f"'{code}'" for code in park_codes])
            park_filter = f"WHERE park_code IN ({park_codes_str})"
        else:
            park_filter = ""

        sql = f"""
        SELECT
            park_code,
            COUNT(*) as total_trails,
            COUNT(CASE WHEN name IS NOT NULL AND name != '' THEN 1 END) as named_trails,
            COUNT(CASE WHEN lengthmiles IS NOT NULL THEN 1 END) as trails_with_length,
            COUNT(CASE WHEN trailtype IS NOT NULL THEN 1 END) as trails_with_type,
            COUNT(CASE WHEN hikerpedestrian IS NOT NULL THEN 1 END) as trails_with_hiker_status,
            COUNT(CASE WHEN primarytrailmaintainer IS NOT NULL THEN 1 END) as trails_with_maintainer,
            COUNT(CASE WHEN nationaltraildesignation IS NOT NULL THEN 1 END) as trails_with_designation,
            COUNT(CASE WHEN geometry IS NOT NULL THEN 1 END) as trails_with_geometry
        FROM tnm_hikes
        {park_filter}
        GROUP BY park_code
        ORDER BY total_trails DESC
        """

        try:
            df = pd.read_sql(sql, self.engine)

            # Calculate completeness percentages
            df["name_completeness"] = (
                df["named_trails"] / df["total_trails"] * 100
            ).round(2)
            df["length_completeness"] = (
                df["trails_with_length"] / df["total_trails"] * 100
            ).round(2)
            df["type_completeness"] = (
                df["trails_with_type"] / df["total_trails"] * 100
            ).round(2)
            df["hiker_status_completeness"] = (
                df["trails_with_hiker_status"] / df["total_trails"] * 100
            ).round(2)
            df["maintainer_completeness"] = (
                df["trails_with_maintainer"] / df["total_trails"] * 100
            ).round(2)
            df["designation_completeness"] = (
                df["trails_with_designation"] / df["total_trails"] * 100
            ).round(2)
            df["geometry_completeness"] = (
                df["trails_with_geometry"] / df["total_trails"] * 100
            ).round(2)

            # Overall quality metrics
            total_trails = df["total_trails"].sum()
            overall_quality = {
                "name_completeness": (
                    df["named_trails"].sum() / total_trails * 100
                ).round(2),
                "length_completeness": (
                    df["trails_with_length"].sum() / total_trails * 100
                ).round(2),
                "type_completeness": (
                    df["trails_with_type"].sum() / total_trails * 100
                ).round(2),
                "hiker_status_completeness": (
                    df["trails_with_hiker_status"].sum() / total_trails * 100
                ).round(2),
                "maintainer_completeness": (
                    df["trails_with_maintainer"].sum() / total_trails * 100
                ).round(2),
                "designation_completeness": (
                    df["trails_with_designation"].sum() / total_trails * 100
                ).round(2),
                "geometry_completeness": (
                    df["trails_with_geometry"].sum() / total_trails * 100
                ).round(2),
            }

            quality_metrics = {
                "park_quality": df.to_dict("records"),
                "overall_quality": overall_quality,
                "summary": {
                    "total_parks": len(df),
                    "total_trails": total_trails,
                    "avg_name_completeness": df["name_completeness"].mean(),
                    "avg_length_completeness": df["length_completeness"].mean(),
                    "avg_geometry_completeness": df["geometry_completeness"].mean(),
                },
            }

            self.logger.info(f"Generated quality metrics for {len(df)} parks")
            return quality_metrics

        except Exception as e:
            self.logger.error(f"Error assessing data quality: {e}")
            return {}

    def get_spatial_analysis(
        self, park_codes: list[str] | None = None
    ) -> Dict[str, Any]:
        """
        Perform spatial analysis on trail data.

        Args:
            park_codes (list[str] | None): List of park codes to analyze.
                                            If None, analyzes all parks.

        Returns:
            Dict containing spatial analysis results
        """
        self.logger.info("Performing spatial analysis")

        # Build SQL query
        if park_codes:
            park_codes_str = ",".join([f"'{code}'" for code in park_codes])
            park_filter = f"WHERE park_code IN ({park_codes_str})"
        else:
            park_filter = ""

        sql = f"""
        SELECT
            park_code,
            COUNT(*) as trail_count,
            ST_Length(ST_Union(geometry)) as total_geometry_length,
            ST_Area(ST_ConvexHull(ST_Union(geometry))) as convex_hull_area,
            ST_AsText(ST_Centroid(ST_Union(geometry))) as centroid
        FROM tnm_hikes
        {park_filter}
        GROUP BY park_code
        ORDER BY trail_count DESC
        """

        try:
            df = pd.read_sql(sql, self.engine)

            # Parse centroid coordinates
            def parse_centroid(centroid_text):
                if centroid_text and centroid_text.startswith("POINT("):
                    coords = (
                        centroid_text.replace("POINT(", "").replace(")", "").split()
                    )
                    return float(coords[0]), float(coords[1])
                return None, None

            df[["centroid_lon", "centroid_lat"]] = df["centroid"].apply(
                lambda x: pd.Series(parse_centroid(x))
            )

            spatial_analysis = {
                "park_spatial": df.to_dict("records"),
                "summary": {
                    "total_parks": len(df),
                    "total_trails": df["trail_count"].sum(),
                    "avg_trails_per_park": df["trail_count"].mean(),
                    "total_geometry_length": df["total_geometry_length"].sum(),
                    "avg_geometry_length_per_park": df["total_geometry_length"].mean(),
                },
            }

            self.logger.info(f"Generated spatial analysis for {len(df)} parks")
            return spatial_analysis

        except Exception as e:
            self.logger.error(f"Error performing spatial analysis: {e}")
            return {}

    def compare_with_osm_data(
        self, park_codes: list[str] | None = None
    ) -> Dict[str, Any]:
        """
        Compare TNM data with OSM data for the same parks.

        Args:
            park_codes (list[str] | None): List of park codes to compare.
                                            If None, compares all parks.

        Returns:
            Dict containing comparison metrics between TNM and OSM data
        """
        self.logger.info("Comparing TNM data with OSM data")

        # Build SQL query
        if park_codes:
            park_codes_str = ",".join([f"'{code}'" for code in park_codes])
            park_filter = f"WHERE t.park_code IN ({park_codes_str})"
        else:
            park_filter = ""

        sql = f"""
        SELECT
            t.park_code,
            COUNT(DISTINCT t.permanentidentifier) as tnm_trail_count,
            COUNT(DISTINCT o.osm_id) as osm_trail_count,
            COALESCE(SUM(t.lengthmiles), 0) as tnm_total_length,
            COALESCE(SUM(o.length_miles), 0) as osm_total_length,
            COALESCE(AVG(t.lengthmiles), 0) as tnm_avg_length,
            COALESCE(AVG(o.length_miles), 0) as osm_avg_length
        FROM tnm_hikes t
        FULL OUTER JOIN osm_hikes o ON t.park_code = o.park_code
        {park_filter}
        GROUP BY t.park_code
        ORDER BY tnm_trail_count DESC
        """

        try:
            df = pd.read_sql(sql, self.engine)

            # Calculate comparison metrics
            df["trail_count_ratio"] = (
                df["tnm_trail_count"] / df["osm_trail_count"]
            ).round(3)
            df["length_ratio"] = (
                df["tnm_total_length"] / df["osm_total_length"]
            ).round(3)
            df["avg_length_ratio"] = (
                df["tnm_avg_length"] / df["osm_avg_length"]
            ).round(3)

            # Handle division by zero
            df["trail_count_ratio"] = df["trail_count_ratio"].replace(
                [float("inf"), -float("inf")], None
            )
            df["length_ratio"] = df["length_ratio"].replace(
                [float("inf"), -float("inf")], None
            )
            df["avg_length_ratio"] = df["avg_length_ratio"].replace(
                [float("inf"), -float("inf")], None
            )

            comparison = {
                "park_comparison": df.to_dict("records"),
                "summary": {
                    "total_parks": len(df),
                    "parks_with_tnm_data": len(df[df["tnm_trail_count"] > 0]),
                    "parks_with_osm_data": len(df[df["osm_trail_count"] > 0]),
                    "parks_with_both": len(
                        df[(df["tnm_trail_count"] > 0) & (df["osm_trail_count"] > 0)]
                    ),
                    "total_tnm_trails": df["tnm_trail_count"].sum(),
                    "total_osm_trails": df["osm_trail_count"].sum(),
                    "total_tnm_length": df["tnm_total_length"].sum(),
                    "total_osm_length": df["osm_total_length"].sum(),
                    "avg_trail_count_ratio": df["trail_count_ratio"].mean(),
                    "avg_length_ratio": df["length_ratio"].mean(),
                },
            }

            self.logger.info(f"Generated comparison for {len(df)} parks")
            return comparison

        except Exception as e:
            self.logger.error(f"Error comparing with OSM data: {e}")
            return {}

    def export_analysis_results(
        self,
        output_dir: str = "profiling_results",
        park_codes: list[str] | None = None,
    ) -> Dict[str, str]:
        """
        Export comprehensive analysis results to files.

        Args:
            output_dir (str): Directory to save analysis results
            park_codes (list[str] | None): List of park codes to analyze.
                                            If None, analyzes all parks.

        Returns:
            Dict containing paths to exported files
        """
        self.logger.info(f"Exporting analysis results to {output_dir}")

        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        exported_files = {}

        try:
            # Export trail statistics
            stats = self.get_trail_statistics(park_codes)
            if stats:
                stats_file = os.path.join(
                    output_dir, f"tnm_trail_statistics_{timestamp}.json"
                )
                pd.DataFrame(stats["park_statistics"]).to_json(
                    stats_file, orient="records", indent=2
                )
                exported_files["trail_statistics"] = stats_file

            # Export trail type breakdown
            type_breakdown = self.get_trail_type_breakdown(park_codes)
            if type_breakdown:
                type_file = os.path.join(
                    output_dir, f"tnm_trail_types_{timestamp}.json"
                )
                pd.DataFrame(type_breakdown["trail_types"]).to_json(
                    type_file, orient="records", indent=2
                )
                exported_files["trail_types"] = type_file

            # Export data quality metrics
            quality = self.get_data_quality_metrics(park_codes)
            if quality:
                quality_file = os.path.join(
                    output_dir, f"tnm_data_quality_{timestamp}.json"
                )
                pd.DataFrame(quality["park_quality"]).to_json(
                    quality_file, orient="records", indent=2
                )
                exported_files["data_quality"] = quality_file

            # Export spatial analysis
            spatial = self.get_spatial_analysis(park_codes)
            if spatial:
                spatial_file = os.path.join(
                    output_dir, f"tnm_spatial_analysis_{timestamp}.json"
                )
                pd.DataFrame(spatial["park_spatial"]).to_json(
                    spatial_file, orient="records", indent=2
                )
                exported_files["spatial_analysis"] = spatial_file

            # Export comparison with OSM
            comparison = self.compare_with_osm_data(park_codes)
            if comparison:
                comparison_file = os.path.join(
                    output_dir, f"tnm_osm_comparison_{timestamp}.json"
                )
                pd.DataFrame(comparison["park_comparison"]).to_json(
                    comparison_file, orient="records", indent=2
                )
                exported_files["osm_comparison"] = comparison_file

            # Export summary report
            summary = {
                "timestamp": timestamp,
                "park_codes_analyzed": park_codes,
                "trail_statistics_summary": stats.get("summary", {}),
                "type_breakdown_summary": type_breakdown.get("summary", {}),
                "quality_summary": quality.get("summary", {}),
                "spatial_summary": spatial.get("summary", {}),
                "comparison_summary": comparison.get("summary", {}),
            }

            summary_file = os.path.join(
                output_dir, f"tnm_analysis_summary_{timestamp}.json"
            )
            with open(summary_file, "w") as f:
                import json

                json.dump(summary, f, indent=2)
            exported_files["summary"] = summary_file

            self.logger.info(f"Exported {len(exported_files)} analysis files")
            return exported_files

        except Exception as e:
            self.logger.error(f"Error exporting analysis results: {e}")
            return {}

    def generate_comprehensive_report(
        self, park_codes: list[str] | None = None
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive analysis report combining all metrics.

        Args:
            park_codes (list[str] | None): List of park codes to analyze.
                                            If None, analyzes all parks.

        Returns:
            Dict containing comprehensive analysis report
        """
        self.logger.info("Generating comprehensive analysis report")

        report = {
            "metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "park_codes_analyzed": park_codes,
                "analysis_type": "TNM Hikes Comprehensive Report",
            },
            "trail_statistics": self.get_trail_statistics(park_codes),
            "trail_type_breakdown": self.get_trail_type_breakdown(park_codes),
            "data_quality_metrics": self.get_data_quality_metrics(park_codes),
            "spatial_analysis": self.get_spatial_analysis(park_codes),
            "osm_comparison": self.compare_with_osm_data(park_codes),
        }

        self.logger.info("Generated comprehensive analysis report")
        return report


def main():
    """Main function for command-line usage."""
    import argparse

    parser = argparse.ArgumentParser(description="TNM Hikes Profiler")
    parser.add_argument(
        "--parks", type=str, help="Comma-separated list of park codes to analyze"
    )
    parser.add_argument(
        "--output-dir", default="profiling_results", help="Output directory for results"
    )
    parser.add_argument("--export", action="store_true", help="Export results to files")
    parser.add_argument("--log-level", default="INFO", help="Logging level")

    args = parser.parse_args()

    # Parse parks list
    park_codes = args.parks.split(",") if args.parks else None

    # Create profiler
    profiler = TNMHikesProfiler(log_level=args.log_level)

    # Generate comprehensive report
    report = profiler.generate_comprehensive_report(park_codes)

    # Print summary (hybrid approach: console + log)
    print("\n=== TNM Hikes Analysis Summary ===")
    profiler.logger.info("=== TNM Hikes Analysis Summary ===")

    if report["trail_statistics"]:
        summary = report["trail_statistics"]["summary"]
        print(f"Total Parks: {summary['total_parks']}")
        print(f"Total Trails: {summary['total_trails']}")
        print(f"Total Length: {summary['total_length_miles']:.2f} miles")
        print(f"Average Trails per Park: {summary['avg_trails_per_park']:.1f}")
        print(f"Average Length per Trail: {summary['avg_length_per_trail']:.2f} miles")

        profiler.logger.info(f"Total Parks: {summary['total_parks']}")
        profiler.logger.info(f"Total Trails: {summary['total_trails']}")
        profiler.logger.info(f"Total Length: {summary['total_length_miles']:.2f} miles")
        profiler.logger.info(
            f"Average Trails per Park: {summary['avg_trails_per_park']:.1f}"
        )
        profiler.logger.info(
            f"Average Length per Trail: {summary['avg_length_per_trail']:.2f} miles"
        )

    if report["data_quality_metrics"]:
        quality = report["data_quality_metrics"]["overall_quality"]
        print(f"\nData Quality:")
        print(f"  Name Completeness: {quality['name_completeness']}%")
        print(f"  Length Completeness: {quality['length_completeness']}%")
        print(f"  Geometry Completeness: {quality['geometry_completeness']}%")

        profiler.logger.info(
            f"Data Quality - Name Completeness: {quality['name_completeness']}%"
        )
        profiler.logger.info(
            f"Data Quality - Length Completeness: {quality['length_completeness']}%"
        )
        profiler.logger.info(
            f"Data Quality - Geometry Completeness: {quality['geometry_completeness']}%"
        )

    if report["osm_comparison"]:
        comparison = report["osm_comparison"]["summary"]
        print(f"\nComparison with OSM:")
        print(f"  TNM Trails: {comparison['total_tnm_trails']}")
        print(f"  OSM Trails: {comparison['total_osm_trails']}")
        print(f"  Parks with Both: {comparison['parks_with_both']}")

        profiler.logger.info(
            f"OSM Comparison - TNM Trails: {comparison['total_tnm_trails']}"
        )
        profiler.logger.info(
            f"OSM Comparison - OSM Trails: {comparison['total_osm_trails']}"
        )
        profiler.logger.info(
            f"OSM Comparison - Parks with Both: {comparison['parks_with_both']}"
        )

    # Export if requested
    if args.export:
        exported_files = profiler.export_analysis_results(args.output_dir, park_codes)
        print(f"\nExported {len(exported_files)} files to {args.output_dir}")
        profiler.logger.info(
            f"Exported {len(exported_files)} files to {args.output_dir}"
        )


if __name__ == "__main__":
    main()

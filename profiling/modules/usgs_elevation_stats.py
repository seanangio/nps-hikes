#!/usr/bin/env python3
"""
USGS Elevation Profiling Module

This module provides profiling capabilities for USGS elevation data,
including elevation statistics, grade analysis, and data quality metrics.
"""

import os
import pandas as pd
from sqlalchemy import text
from typing import Dict, Any

from ..utils import (
    get_db_connection,
    save_results,
    ProfilingLogger,
    load_sql_query,
)


class USGSElevationProfiler:
    """USGS elevation profiling module."""

    def __init__(self):
        self.logger = ProfilingLogger("usgs_elevation")
        self.engine = get_db_connection()

    def run_trail_elevation_stats(self) -> Dict[str, Any]:
        """Run trail-level elevation statistics analysis."""
        self.logger.info("Running trail elevation statistics analysis")

        query = load_sql_query("usgs_elevation", "trail_elevation_stats.sql")

        with self.engine.connect() as conn:
            df = pd.read_sql(query, conn)

        save_results(
            df, "trail_stats.csv", output_dir="profiling_results/usgs_elevation"
        )
        self.logger.success(f"Trail elevation stats: {len(df)} trails analyzed")

        return {"trail_count": len(df)}

    def run_park_elevation_summary(self) -> Dict[str, Any]:
        """Run park-level elevation summary analysis."""
        self.logger.info("Running park elevation summary analysis")

        query = load_sql_query("usgs_elevation", "park_elevation_summary.sql")

        with self.engine.connect() as conn:
            df = pd.read_sql(query, conn)

        save_results(
            df, "park_summary.csv", output_dir="profiling_results/usgs_elevation"
        )
        self.logger.success(f"Park elevation summary: {len(df)} parks analyzed")

        return {"park_count": len(df)}

    def run_trail_grades(self) -> Dict[str, Any]:
        """Run trail grade analysis."""
        self.logger.info("Running trail grade analysis")

        query = load_sql_query("usgs_elevation", "trail_grades.sql")

        with self.engine.connect() as conn:
            df = pd.read_sql(query, conn)

        save_results(
            df, "trail_grades.csv", output_dir="profiling_results/usgs_elevation"
        )
        self.logger.success(f"Trail grades: {len(df)} trails analyzed")

        return {"trail_count": len(df)}

    def run_steepest_segments(self) -> Dict[str, Any]:
        """Run steepest segments analysis."""
        self.logger.info("Running steepest segments analysis")

        query = load_sql_query("usgs_elevation", "steepest_segments.sql")

        with self.engine.connect() as conn:
            df = pd.read_sql(query, conn)

        save_results(
            df, "steepest_segments.csv", output_dir="profiling_results/usgs_elevation"
        )
        self.logger.success(f"Steepest segments: {len(df)} segments analyzed")

        return {"segment_count": len(df)}

    def run_data_quality(self) -> Dict[str, Any]:
        """Run data quality analysis."""
        self.logger.info("Running data quality analysis")

        query = load_sql_query("usgs_elevation", "data_quality.sql")

        with self.engine.connect() as conn:
            df = pd.read_sql(query, conn)

        save_results(
            df, "data_quality.csv", output_dir="profiling_results/usgs_elevation"
        )
        self.logger.success(f"Data quality: {len(df)} parks analyzed")

        return {"park_count": len(df)}

    def run_all(self) -> Dict[str, Any]:
        """Run all USGS elevation profiling analyses."""
        self.logger.info("Starting USGS elevation profiling")

        all_results = {}

        try:
            all_results["trail_stats"] = self.run_trail_elevation_stats()
            all_results["park_summary"] = self.run_park_elevation_summary()
            all_results["trail_grades"] = self.run_trail_grades()
            all_results["steepest_segments"] = self.run_steepest_segments()
            all_results["data_quality"] = self.run_data_quality()
            # Skip collection_status for now due to pandas/sqlalchemy issue

            self.logger.success("All USGS elevation profiling completed successfully")

        except Exception as e:
            self.logger.error(f"Error in USGS elevation profiling: {e}")
            raise

        return all_results


def run_usgs_elevation_stats():
    """Top-level function for USGS elevation profiling."""
    profiler = USGSElevationProfiler()
    return profiler.run_all()


# Keep old name for backwards compatibility
run_usgs_elevation = run_usgs_elevation_stats


if __name__ == "__main__":
    run_usgs_elevation_stats()

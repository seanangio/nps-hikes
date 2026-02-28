#!/usr/bin/env python3
"""
Trail Matching Profiling Module

This module provides analysis and profiling capabilities for trail matching results,
including match performance, confidence distributions, and quality metrics.
"""

from typing import Any

from ..config import PROFILING_MODULES, PROFILING_SETTINGS
from ..utils import (
    ProfilingLogger,
    get_db_connection,
    load_sql_query,
    print_results_summary,
    run_query,
    save_results,
)


class TrailMatchingProfiler:
    """Trail matching profiling module."""

    def __init__(self) -> None:
        self.config = PROFILING_MODULES["trail_matching"]
        self.logger = ProfilingLogger("trail_matching")
        self.results: dict[str, Any] = {}

    def run_match_summary(self) -> None:
        """Run trail matching summary analysis."""
        try:
            self.logger.info("Running trail matching summary analysis...")

            engine = get_db_connection()
            query = load_sql_query("trail_matching", "match_summary.sql")
            results_df = run_query(engine, query)

            save_results(results_df, "trail_matching_match_summary.csv")
            print_results_summary(results_df, "Trail Matching Summary")

            self.results["match_summary"] = len(results_df)
            self.logger.success("Trail matching summary analysis completed")

        except Exception as e:
            self.logger.error(f"Failed to run trail matching summary: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise

    def run_confidence_distribution(self) -> None:
        """Run confidence score distribution analysis."""
        try:
            self.logger.info("Running confidence distribution analysis...")

            engine = get_db_connection()
            query = load_sql_query("trail_matching", "confidence_distribution.sql")
            results_df = run_query(engine, query)

            save_results(results_df, "trail_matching_confidence_distribution.csv")
            print_results_summary(results_df, "Confidence Distribution")

            self.results["confidence_distribution"] = len(results_df)
            self.logger.success("Confidence distribution analysis completed")

        except Exception as e:
            self.logger.error(f"Failed to run confidence distribution: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise

    def run_park_analysis(self) -> None:
        """Run park-level trail matching analysis."""
        try:
            self.logger.info("Running park-level trail matching analysis...")

            engine = get_db_connection()
            query = load_sql_query("trail_matching", "park_analysis.sql")
            results_df = run_query(engine, query)

            save_results(results_df, "trail_matching_park_analysis.csv")
            print_results_summary(results_df, "Park-Level Trail Matching Analysis")

            self.results["park_analysis"] = len(results_df)
            self.logger.success("Park-level trail matching analysis completed")

        except Exception as e:
            self.logger.error(f"Failed to run park analysis: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise

    def run_distance_analysis(self) -> None:
        """Run distance analysis for trail matching."""
        try:
            self.logger.info("Running distance analysis...")

            engine = get_db_connection()
            query = load_sql_query("trail_matching", "distance_analysis.sql")
            results_df = run_query(engine, query)

            save_results(results_df, "trail_matching_distance_analysis.csv")
            print_results_summary(results_df, "Distance Analysis")

            self.results["distance_analysis"] = len(results_df)
            self.logger.success("Distance analysis completed")

        except Exception as e:
            self.logger.error(f"Failed to run distance analysis: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise

    def run_unmatched_analysis(self) -> None:
        """Run analysis of unmatched points."""
        try:
            self.logger.info("Running unmatched points analysis...")

            engine = get_db_connection()
            query = load_sql_query("trail_matching", "unmatched_analysis.sql")
            results_df = run_query(engine, query)

            save_results(results_df, "trail_matching_unmatched_analysis.csv")
            print_results_summary(results_df, "Unmatched Points Analysis")

            self.results["unmatched_analysis"] = len(results_df)
            self.logger.success("Unmatched points analysis completed")

        except Exception as e:
            self.logger.error(f"Failed to run unmatched analysis: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise

    def run_source_comparison(self) -> None:
        """Run TNM vs OSM source comparison analysis."""
        try:
            self.logger.info("Running source comparison analysis...")

            engine = get_db_connection()
            query = load_sql_query("trail_matching", "source_comparison.sql")
            results_df = run_query(engine, query)

            save_results(results_df, "trail_matching_source_comparison.csv")
            print_results_summary(results_df, "Source Comparison Analysis")

            self.results["source_comparison"] = len(results_df)
            self.logger.success("Source comparison analysis completed")

        except Exception as e:
            self.logger.error(f"Failed to run source comparison: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise

    def run_all(self) -> dict[str, Any]:
        """Run all trail matching profiling analyses."""
        self.run_match_summary()
        self.run_confidence_distribution()
        self.run_park_analysis()
        self.run_distance_analysis()
        self.run_unmatched_analysis()
        self.run_source_comparison()
        return self.results


# Convenience function
def run_trail_matching_profiling() -> dict[str, Any]:
    """Convenience function to run trail matching profiling."""
    profiler = TrailMatchingProfiler()
    return profiler.run_all()


def run_trail_matching() -> dict[str, Any]:
    """Top-level function to run trail matching profiling."""
    profiler = TrailMatchingProfiler()
    return profiler.run_all()


if __name__ == "__main__":
    run_trail_matching_profiling()

#!/usr/bin/env python3
"""
Google Maps Hiking Locations Profiling Module

This module provides analysis and profiling capabilities for Google Maps hiking
location data, including summary statistics and park-level analysis.
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


class GMapsHikingLocationsProfiler:
    """Google Maps hiking locations profiling module."""

    def __init__(self) -> None:
        self.config = PROFILING_MODULES["gmaps_hiking_locations"]
        self.logger = ProfilingLogger("gmaps_hiking_locations")
        self.results: dict[str, Any] = {}

    def run_basic_summary(self) -> None:
        """Run basic summary analysis."""
        try:
            self.logger.info("Running basic summary analysis...")
            query = load_sql_query("gmaps_hiking_locations", "basic_summary.sql")
            engine = get_db_connection()
            results = run_query(engine, query)

            if not results.empty:
                save_results(
                    results,
                    "gmaps_basic_summary.csv",
                    PROFILING_SETTINGS["output_directory"],
                    self.config.get("output_prefix", "gmaps"),
                )
                self.results["basic_summary"] = results
                self.logger.success("Basic summary analysis completed")

                if PROFILING_SETTINGS["print_summaries"]:
                    print_results_summary(
                        results, "Google Maps Hiking Locations Summary"
                    )
            else:
                self.logger.error("No results for basic summary analysis")

        except Exception as e:
            self.logger.error(f"Failed to run basic summary: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise

    def run_park_analysis(self) -> None:
        """Run park-level analysis."""
        try:
            self.logger.info("Running park-level analysis...")
            query = load_sql_query("gmaps_hiking_locations", "park_analysis.sql")
            engine = get_db_connection()
            results = run_query(engine, query)

            if not results.empty:
                save_results(
                    results,
                    "gmaps_park_analysis.csv",
                    PROFILING_SETTINGS["output_directory"],
                    self.config.get("output_prefix", "gmaps"),
                )

                self.results["park_analysis"] = results
                self.logger.success("Park-level analysis completed")

                if PROFILING_SETTINGS["print_summaries"]:
                    print_results_summary(results, "Park Analysis")
            else:
                self.logger.error("No results for park analysis")

        except Exception as e:
            self.logger.error(f"Failed to run park analysis: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise

    def run_park_coverage(self) -> None:
        """Run park coverage analysis."""
        try:
            self.logger.info("Running park coverage analysis...")
            query = load_sql_query("gmaps_hiking_locations", "park_coverage.sql")
            engine = get_db_connection()
            results = run_query(engine, query)

            if not results.empty:
                save_results(
                    results,
                    "gmaps_park_coverage.csv",
                    PROFILING_SETTINGS["output_directory"],
                    self.config.get("output_prefix", "gmaps"),
                )

                self.results["park_coverage"] = results
                self.logger.success("Park coverage analysis completed")

                if PROFILING_SETTINGS["print_summaries"]:
                    print_results_summary(results, "Park Coverage Analysis")
            else:
                self.logger.error("No results for park coverage analysis")

        except Exception as e:
            self.logger.error(f"Failed to run park coverage analysis: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise

    def run_all(self) -> dict[str, Any]:
        """Run all profiling methods."""
        try:
            self.logger.info("Starting Google Maps hiking locations profiling...")

            # Run basic summary
            self.run_basic_summary()

            # Run park analysis
            self.run_park_analysis()

            # Run park coverage analysis
            self.run_park_coverage()

            self.logger.success(
                "Google Maps hiking locations profiling completed successfully"
            )
            return self.results

        except Exception as e:
            self.logger.error(f"Profiling failed: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise
            return {}


def run_gmaps_hiking_locations() -> dict[str, Any]:
    """Top-level function to run Google Maps hiking locations profiling."""
    profiler = GMapsHikingLocationsProfiler()
    return profiler.run_all()


if __name__ == "__main__":
    # Test the module
    profiler = GMapsHikingLocationsProfiler()

    try:
        # Run basic summary
        profiler.run_basic_summary()

        # Run park analysis
        profiler.run_park_analysis()

        # Run park coverage analysis
        profiler.run_park_coverage()

        print("Google Maps hiking locations profiling completed successfully!")

    except Exception as e:
        print(f"Profiling failed: {e}")

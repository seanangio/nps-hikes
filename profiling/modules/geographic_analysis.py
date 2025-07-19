"""
Geographic analysis profiling module.

This module provides geographic and spatial analysis queries for NPS park data.
"""

from ..utils import (
    get_db_connection,
    load_sql_query,
    run_query,
    save_results,
    print_results_summary,
    ProfilingLogger,
)
from ..config import PROFILING_MODULES, PROFILING_SETTINGS


class GeographicAnalysisProfiler:
    """Geographic analysis profiling module."""

    def __init__(self):
        self.config = PROFILING_MODULES["geographic_analysis"]
        self.logger = ProfilingLogger("geographic_analysis")
        self.results = {}

    def run_regional_breakdown(self):
        """Run regional breakdown query."""
        try:
            query = load_sql_query("geographic_analysis", "regional_breakdown.sql")
            engine = get_db_connection()
            results = run_query(engine, query)

            if not results.empty:
                save_results(
                    results,
                    "regional_breakdown.csv",
                    PROFILING_SETTINGS["output_directory"],
                    self.config["output_prefix"],
                )
                if PROFILING_SETTINGS["print_summaries"]:
                    print_results_summary(results, "Regional Breakdown")
                self.results["regional_breakdown"] = results
                self.logger.success("Regional breakdown")
            else:
                self.logger.error("No results for regional breakdown")

        except Exception as e:
            self.logger.error(f"Failed to run regional breakdown: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise

    def run_coordinate_quality(self):
        """Run coordinate quality query."""
        try:
            query = load_sql_query("geographic_analysis", "coordinate_quality.sql")
            engine = get_db_connection()
            results = run_query(engine, query)

            if not results.empty:
                save_results(
                    results,
                    "coordinate_quality.csv",
                    PROFILING_SETTINGS["output_directory"],
                    self.config["output_prefix"],
                )
                if PROFILING_SETTINGS["print_summaries"]:
                    print_results_summary(results, "Coordinate Quality")
                self.results["coordinate_quality"] = results
                self.logger.success("Coordinate quality")
            else:
                self.logger.error("No results for coordinate quality")

        except Exception as e:
            self.logger.error(f"Failed to run coordinate quality: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise

    def run_boundary_coverage(self):
        """Run boundary coverage query."""
        try:
            query = load_sql_query("geographic_analysis", "boundary_coverage.sql")
            engine = get_db_connection()
            results = run_query(engine, query)

            if not results.empty:
                save_results(
                    results,
                    "boundary_coverage.csv",
                    PROFILING_SETTINGS["output_directory"],
                    self.config["output_prefix"],
                )
                if PROFILING_SETTINGS["print_summaries"]:
                    print_results_summary(results, "Boundary Coverage")
                self.results["boundary_coverage"] = results
                self.logger.success("Boundary coverage")
            else:
                self.logger.error("No results for boundary coverage")

        except Exception as e:
            self.logger.error(f"Failed to run boundary coverage: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise

    def run_all(self):
        """Run all geographic analysis queries."""
        # Run each query defined in config
        for query_file in self.config["queries"]:
            query_name = query_file.replace(".sql", "")
            method_name = f"run_{query_name}"

            if hasattr(self, method_name):
                getattr(self, method_name)()
            else:
                self.logger.error(f"No method found for query: {query_name}")

        return self.results


# Convenience function for external use
def run_geographic_analysis():
    """Convenience function to run geographic analysis profiling."""
    profiler = GeographicAnalysisProfiler()
    return profiler.run_all()


if __name__ == "__main__":
    run_geographic_analysis()

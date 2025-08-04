"""
OSM hiking trails profiling module.

This module analyzes data from the osm_hikes table populated by osm_hikes_collector.py.
It provides insights into trail counts, lengths, types, and data quality from OSM sources.
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


class OSMHikesProfiler:
    """OSM hiking trails profiling module."""

    def __init__(self):
        self.config = PROFILING_MODULES["osm_hikes"]
        self.logger = ProfilingLogger("osm_hikes")
        self.results = {}

    def run_trails_summary_by_park(self):
        """Run trails summary by park query."""
        try:
            query = load_sql_query("osm_hikes", "trails_summary_by_park.sql")
            engine = get_db_connection()
            results = run_query(engine, query)

            if not results.empty:
                save_results(
                    results,
                    "trails_summary_by_park.csv",
                    PROFILING_SETTINGS["output_directory"],
                    self.config["output_prefix"],
                )
                if PROFILING_SETTINGS["print_summaries"]:
                    print_results_summary(results, "Trails Summary by Park")
                self.results["trails_summary"] = results
                self.logger.success("Trails summary by park")
            else:
                self.logger.error("No results for trails summary by park")

        except Exception as e:
            self.logger.error(f"Failed to run trails summary: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise

    def run_trail_type_analysis(self):
        """Run trail type analysis query."""
        try:
            query = load_sql_query("osm_hikes", "trail_type_analysis.sql")
            engine = get_db_connection()
            results = run_query(engine, query)

            if not results.empty:
                save_results(
                    results,
                    "trail_type_analysis.csv",
                    PROFILING_SETTINGS["output_directory"],
                    self.config["output_prefix"],
                )
                if PROFILING_SETTINGS["print_summaries"]:
                    print_results_summary(results, "Trail Type Analysis")
                self.results["trail_types"] = results
                self.logger.success("Trail type analysis")
            else:
                self.logger.error("No results for trail type analysis")

        except Exception as e:
            self.logger.error(f"Failed to run trail type analysis: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise

    def run_trail_length_distribution(self):
        """Run trail length distribution query."""
        try:
            query = load_sql_query("osm_hikes", "trail_length_distribution.sql")
            engine = get_db_connection()
            results = run_query(engine, query)

            if not results.empty:
                save_results(
                    results,
                    "trail_length_distribution.csv",
                    PROFILING_SETTINGS["output_directory"],
                    self.config["output_prefix"],
                )
                if PROFILING_SETTINGS["print_summaries"]:
                    print_results_summary(results, "Trail Length Distribution")
                self.results["length_distribution"] = results
                self.logger.success("Trail length distribution")
            else:
                self.logger.error("No results for trail length distribution")

        except Exception as e:
            self.logger.error(f"Failed to run trail length distribution: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise

    def run_trail_data_quality(self):
        """Run trail data quality checks."""
        try:
            query = load_sql_query("osm_hikes", "trail_data_quality.sql")
            engine = get_db_connection()
            results = run_query(engine, query)

            if not results.empty:
                save_results(
                    results,
                    "trail_data_quality.csv",
                    PROFILING_SETTINGS["output_directory"],
                    self.config["output_prefix"],
                )
                if PROFILING_SETTINGS["print_summaries"]:
                    print_results_summary(results, "Trail Data Quality")
                self.results["data_quality"] = results
                self.logger.success("Trail data quality checks")
            else:
                self.logger.error("No results for trail data quality checks")

        except Exception as e:
            self.logger.error(f"Failed to run trail data quality checks: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise

    def run_all(self):
        """Run all OSM hikes profiling queries."""
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
def run_osm_hikes():
    """Convenience function to run OSM hikes profiling."""
    profiler = OSMHikesProfiler()
    return profiler.run_all()


if __name__ == "__main__":
    run_osm_hikes()
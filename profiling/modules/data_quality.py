"""
Data quality profiling module.

This module performs cross-table validation and data integrity checks across
the parks, park_boundaries, and osm_hikes tables. It focuses on referential
integrity, consistency, and duplicate detection that spans multiple tables.
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


class DataQualityProfiler:
    """Data quality profiling module."""

    def __init__(self) -> None:
        self.config = PROFILING_MODULES["data_quality"]
        self.logger = ProfilingLogger("data_quality")
        self.results: dict[str, Any] = {}

    def run_referential_integrity(self) -> None:
        """Run referential integrity checks."""
        try:
            query = load_sql_query("data_quality", "referential_integrity.sql")
            engine = get_db_connection()
            results = run_query(engine, query)

            if not results.empty:
                save_results(
                    results,
                    "referential_integrity.csv",
                    PROFILING_SETTINGS["output_directory"],
                    self.config["output_prefix"],
                )
                if PROFILING_SETTINGS["print_summaries"]:
                    print_results_summary(results, "Referential Integrity Checks")
                self.results["referential_integrity"] = results
                self.logger.success("Referential integrity checks")
            else:
                self.logger.error("No results for referential integrity checks")

        except Exception as e:
            self.logger.error(f"Failed to run referential integrity checks: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise

    def run_data_consistency(self) -> None:
        """Run data consistency checks."""
        try:
            query = load_sql_query("data_quality", "data_consistency.sql")
            engine = get_db_connection()
            results = run_query(engine, query)

            if not results.empty:
                save_results(
                    results,
                    "data_consistency.csv",
                    PROFILING_SETTINGS["output_directory"],
                    self.config["output_prefix"],
                )
                if PROFILING_SETTINGS["print_summaries"]:
                    print_results_summary(results, "Data Consistency Checks")
                self.results["data_consistency"] = results
                self.logger.success("Data consistency checks")
            else:
                self.logger.error("No results for data consistency checks")

        except Exception as e:
            self.logger.error(f"Failed to run data consistency checks: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise

    def run_missing_data_summary(self) -> None:
        """Run missing data summary analysis."""
        try:
            query = load_sql_query("data_quality", "missing_data_summary.sql")
            engine = get_db_connection()
            results = run_query(engine, query)

            if not results.empty:
                save_results(
                    results,
                    "missing_data_summary.csv",
                    PROFILING_SETTINGS["output_directory"],
                    self.config["output_prefix"],
                )
                if PROFILING_SETTINGS["print_summaries"]:
                    print_results_summary(results, "Missing Data Summary")
                self.results["missing_data_summary"] = results
                self.logger.success("Missing data summary")
            else:
                self.logger.error("No results for missing data summary")

        except Exception as e:
            self.logger.error(f"Failed to run missing data summary: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise

    def run_duplicate_detection(self) -> None:
        """Run duplicate detection analysis."""
        try:
            query = load_sql_query("data_quality", "duplicate_detection.sql")
            engine = get_db_connection()
            results = run_query(engine, query)

            if not results.empty:
                save_results(
                    results,
                    "duplicate_detection.csv",
                    PROFILING_SETTINGS["output_directory"],
                    self.config["output_prefix"],
                )
                if PROFILING_SETTINGS["print_summaries"]:
                    print_results_summary(results, "Duplicate Detection")
                self.results["duplicate_detection"] = results
                self.logger.success("Duplicate detection")
            else:
                self.logger.error("No results for duplicate detection")

        except Exception as e:
            self.logger.error(f"Failed to run duplicate detection: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise

    def run_all(self) -> dict[str, Any]:
        """Run all data quality checks."""
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
def run_data_quality() -> dict[str, Any]:
    """Convenience function to run data quality profiling."""
    profiler = DataQualityProfiler()
    return profiler.run_all()


if __name__ == "__main__":
    run_data_quality()

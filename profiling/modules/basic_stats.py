"""
Basic statistics profiling module.

This module demonstrates the standard pattern for profiling modules:
1. Load configuration
2. Execute queries
3. Save results
4. Handle errors gracefully
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


class BasicStatsProfiler:
    """Basic statistics profiling module."""

    def __init__(self):
        self.config = PROFILING_MODULES["basic_stats"]
        self.logger = ProfilingLogger("basic_stats")
        self.results = {}

    def run_park_counts_by_state(self):
        """Run park counts by state query."""
        try:
            query = load_sql_query("basic_stats", "park_counts_by_state.sql")
            engine = get_db_connection()
            results = run_query(engine, query)

            if not results.empty:
                save_results(
                    results,
                    "park_counts_by_state.csv",
                    PROFILING_SETTINGS["output_directory"],
                    self.config["output_prefix"],
                )
                if PROFILING_SETTINGS["print_summaries"]:
                    print_results_summary(results, "Park Counts by State")
                self.results["park_counts"] = results
                self.logger.success("Park counts by state")
            else:
                self.logger.error("No results for park counts by state")

        except Exception as e:
            self.logger.error(f"Failed to run park counts: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise

    def run_collection_status_summary(self):
        """Run collection status summary query."""
        try:
            query = load_sql_query("basic_stats", "collection_status_summary.sql")
            engine = get_db_connection()
            results = run_query(engine, query)

            if not results.empty:
                save_results(
                    results,
                    "collection_status_summary.csv",
                    PROFILING_SETTINGS["output_directory"],
                    self.config["output_prefix"],
                )
                if PROFILING_SETTINGS["print_summaries"]:
                    print_results_summary(results, "Collection Status Summary")
                self.results["collection_status"] = results
                self.logger.success("Collection status summary")
            else:
                self.logger.error("No results for collection status summary")

        except Exception as e:
            self.logger.error(f"Failed to run collection status: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise

    def run_data_completeness_summary(self):
        """Run data completeness summary query."""
        try:
            query = load_sql_query("basic_stats", "data_completeness_summary.sql")
            engine = get_db_connection()
            results = run_query(engine, query)

            if not results.empty:
                save_results(
                    results,
                    "data_completeness_summary.csv",
                    PROFILING_SETTINGS["output_directory"],
                    self.config["output_prefix"],
                )
                if PROFILING_SETTINGS["print_summaries"]:
                    print_results_summary(results, "Data Completeness Summary")
                self.results["data_completeness"] = results
                self.logger.success("Data completeness summary")
            else:
                self.logger.error("No results for data completeness summary")

        except Exception as e:
            self.logger.error(f"Failed to run data completeness: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise

    def run_all(self):
        """Run all basic statistics queries."""
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
def run_basic_stats():
    """Convenience function to run basic stats profiling."""
    profiler = BasicStatsProfiler()
    return profiler.run_all()


if __name__ == "__main__":
    run_basic_stats()

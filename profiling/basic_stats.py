"""
Basic statistics and summary queries for NPS park data.

This module provides fundamental data profiling queries including:
- Park counts by state
- Collection status summaries
- Data completeness metrics
"""

from .utils import get_db_connection, load_sql_query, run_query, save_results, print_results_summary


def get_park_counts_by_state():
    """
    Get park counts by state with coordinate coverage and collection success rates.
    
    Returns:
        pd.DataFrame: Results with state-level park statistics
    """
    query = load_sql_query("park_counts_by_state.sql")    
    engine = get_db_connection()
    results = run_query(engine, query)
    save_results(results, "park_counts_by_state.csv")
    print_results_summary(results, "Park Counts by State")
    return results


def get_collection_status_summary():
    """
    Get overall collection success/failure summary.
    
    Returns:
        pd.DataFrame: Results with collection status breakdown
    """
    query = load_sql_query("collection_status_summary.sql")
    engine = get_db_connection()
    results = run_query(engine, query)
    save_results(results, "collection_status_summary.csv")
    print_results_summary(results, "Collection Status Summary")
    return results


def get_data_completeness_summary():
    """
    Get data completeness metrics for all parks.
    
    Returns:
        pd.DataFrame: Results with completeness statistics
    """
    query = load_sql_query("data_completeness_summary.sql")
    engine = get_db_connection()
    results = run_query(engine, query)
    save_results(results, "data_completeness_summary.csv")
    print_results_summary(results, "Data Completeness Summary")
    return results


def get_visit_date_distribution():
    """
    Get distribution of parks by visit month and year.
    
    Returns:
        pd.DataFrame: Results with visit date patterns
    """
    query = """
    SELECT 
        visit_month,
        visit_year,
        COUNT(*) as park_count
    FROM parks 
    WHERE visit_month IS NOT NULL AND visit_year IS NOT NULL
    GROUP BY visit_month, visit_year
    ORDER BY visit_year, visit_month
    """
    
    engine = get_db_connection()
    results = run_query(engine, query)
    save_results(results, "visit_date_distribution.csv")
    print_results_summary(results, "Visit Date Distribution")
    return results


def run_all_basic_stats():
    """
    Run all basic statistics queries and save results.
    
    This function executes all basic profiling queries and saves
    the results to CSV files in the profiling_results directory.
    """
    print("Running basic statistics profiling...")
    print("=" * 50)
    
    get_park_counts_by_state()
    get_collection_status_summary()
    get_data_completeness_summary()
    #get_visit_date_distribution()
    
    print("Basic statistics profiling complete!")
    print("Results saved to profiling_results/ directory")


if __name__ == "__main__":
    run_all_basic_stats() 
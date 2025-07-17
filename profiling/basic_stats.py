"""
Basic statistics and summary queries for NPS park data.

This module provides fundamental data profiling queries including:
- Park counts by state
- Collection status summaries
- Data completeness metrics
"""

from .utils import get_db_connection, run_query, save_results, print_results_summary


def get_park_counts_by_state():
    """
    Get park counts by state with coordinate coverage and collection success rates.
    
    Returns:
        pd.DataFrame: Results with state-level park statistics
    """
    query = """
    SELECT 
        TRIM(unnest(string_to_array(states, ','))) as individual_state,
        COUNT(*) as park_count,
        COUNT(CASE WHEN latitude IS NOT NULL THEN 1 END) as parks_with_coords,
        COUNT(CASE WHEN collection_status = 'success' THEN 1 END) as successful_collections,
        ROUND(COUNT(CASE WHEN latitude IS NOT NULL THEN 1 END) * 100.0 / COUNT(*), 1) as coord_coverage_pct,
        ROUND(COUNT(CASE WHEN collection_status = 'success' THEN 1 END) * 100.0 / COUNT(*), 1) as success_rate_pct
    FROM parks 
    WHERE states IS NOT NULL 
        AND states != '' 
        AND states != 'null'
    GROUP BY TRIM(unnest(string_to_array(states, ',')))
    ORDER BY park_count DESC
    """
    
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
    query = """
    SELECT 
        collection_status,
        COUNT(*) as count,
        ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) as percentage
    FROM parks 
    GROUP BY collection_status
    ORDER BY count DESC
    """
    
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
    query = """
    SELECT 
        COUNT(*) as total_parks,
        COUNT(CASE WHEN park_code IS NOT NULL AND park_code != '' THEN 1 END) as parks_with_codes,
        COUNT(CASE WHEN full_name IS NOT NULL AND full_name != '' THEN 1 END) as parks_with_names,
        COUNT(CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL THEN 1 END) as parks_with_coords,
        COUNT(CASE WHEN description IS NOT NULL AND description != '' THEN 1 END) as parks_with_descriptions,
        COUNT(CASE WHEN url IS NOT NULL AND url != '' THEN 1 END) as parks_with_urls,
        ROUND(COUNT(CASE WHEN park_code IS NOT NULL AND park_code != '' THEN 1 END) * 100.0 / COUNT(*), 1) as code_completeness_pct,
        ROUND(COUNT(CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL THEN 1 END) * 100.0 / COUNT(*), 1) as coord_completeness_pct,
        ROUND(COUNT(CASE WHEN description IS NOT NULL AND description != '' THEN 1 END) * 100.0 / COUNT(*), 1) as desc_completeness_pct
    FROM parks
    """
    
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
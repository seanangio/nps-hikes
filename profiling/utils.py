"""
Shared utilities for data profiling.

This module provides common functions for database connections,
query execution, and result handling across all profiling scripts.
"""

import os
import pandas as pd
from sqlalchemy import text
from nps_db_writer import get_postgres_engine


def get_db_connection():
    """
    Get database connection using existing environment setup.
    
    Returns:
        sqlalchemy.engine.Engine: SQLAlchemy engine instance
    """
    return get_postgres_engine()


def run_query(engine, query, params=None):
    """
    Execute a query and return results as DataFrame.
    
    Args:
        engine: SQLAlchemy engine instance
        query (str): SQL query to execute
        params (dict, optional): Query parameters
        
    Returns:
        pd.DataFrame: Query results as DataFrame
    """
    try:
        with engine.connect() as conn:
            result = conn.execute(text(query), params or {})
            return pd.DataFrame(result.fetchall(), columns=result.keys())
    except Exception as e:
        print(f"Query failed: {e}")
        return pd.DataFrame()


def save_results(df, filename, output_dir="profiling_results"):
    """
    Save profiling results to CSV.
    
    Args:
        df (pd.DataFrame): Results to save
        filename (str): Output filename
        output_dir (str): Directory to save results in
    """
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)
    df.to_csv(filepath, index=False)
    print(f"Results saved to: {filepath}")


def print_results_summary(df, title):
    """
    Print a formatted summary of query results.
    
    Args:
        df (pd.DataFrame): Results to summarize
        title (str): Title for the summary
    """
    print(f"\n=== {title} ===")
    if df.empty:
        print("No results found.")
    else:
        print(f"Found {len(df)} records:")
        print(df.to_string(index=False))
    print() 
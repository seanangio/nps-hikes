"""
Enhanced utilities for the profiling system.
"""

import os
import pandas as pd
from sqlalchemy import text
from dotenv import load_dotenv
from config.settings import config
from nps_db_writer import get_postgres_engine

# Load environment variables
load_dotenv()


def get_db_connection():
    """Get database connection using existing environment setup."""
    try:
        return get_postgres_engine()
    except ValueError as e:
        print(f"Database connection failed: {e}")
        print(
            "Please ensure your .env file contains the required database credentials:"
        )
        print(
            "  POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD"
        )
        raise


def load_sql_query(module_name, query_filename):
    """
    Load SQL query from the appropriate module directory.

    Args:
        module_name (str): Name of the module (e.g., 'basic_stats')
        query_filename (str): Name of the SQL file

    Returns:
        str: SQL query content
    """
    # Build path to the specific module's query directory
    current_dir = os.path.dirname(__file__)
    query_path = os.path.join(current_dir, "queries", module_name, query_filename)

    if not os.path.exists(query_path):
        raise FileNotFoundError(f"SQL query not found: {query_path}")

    with open(query_path, "r") as f:
        return f.read().strip()


def run_query(engine, query, params=None):
    """Execute a query and return results as DataFrame."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text(query), params or {})
            return pd.DataFrame(result.fetchall(), columns=result.keys())
    except Exception as e:
        print(f"Query failed: {e}")
        return pd.DataFrame()


def save_results(df, filename, output_dir="profiling_results", prefix=""):
    """Save profiling results to CSV with optional prefix."""
    os.makedirs(output_dir, exist_ok=True)

    if prefix:
        filename = f"{prefix}_{filename}"

    filepath = os.path.join(output_dir, filename)
    df.to_csv(filepath, index=False)
    # Removed verbose file save message - files are saved silently


def print_results_summary(df, title):
    """Print a formatted summary of query results."""
    print(f"\n=== {title} ===")
    if df.empty:
        print("No results found.")
    else:
        print(f"Found {len(df)} records:")
        print(df.to_string(index=False))
    print()


class ProfilingLogger:
    """Simple logging for profiling operations."""

    def __init__(self, module_name):
        self.module_name = module_name

    def info(self, message):
        print(f"[{self.module_name}] {message}")

    def error(self, message):
        print(f"[{self.module_name}] ERROR: {message}")

    def success(self, message):
        print(f"[{self.module_name}] ✓ {message}")

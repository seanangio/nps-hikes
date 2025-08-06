"""
Data Freshness Monitoring Module

This module provides comprehensive monitoring of data freshness across all tables
in the NPS Hikes project. It checks when data was last collected and categorizes
it as Fresh, Warning, or Stale based on configurable thresholds.

Key Features:
- Monitors all 4 tables: parks, park_boundaries, osm_hikes, tnm_hikes
- Park-level summaries for trail data (OSM/TNM)
- Configurable staleness thresholds
- Comprehensive reporting with statistics
- Easy integration with existing profiling system
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
import pandas as pd
from sqlalchemy import Engine, text
from dotenv import load_dotenv

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))

# Add project root to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from config.settings import config
from db_writer import get_postgres_engine


class DataFreshnessMonitor:
    """
    Monitor data freshness across all tables in the NPS Hikes project.
    
    This class provides methods to check when data was last collected
    and categorize it based on staleness thresholds.
    """
    
    def __init__(self, engine: Optional[Engine] = None):
        """
        Initialize the data freshness monitor.
        
        Args:
            engine (Optional[Engine]): SQLAlchemy engine. If None, creates one from config.
        """
        self.engine = engine or get_postgres_engine()
        self.fresh_threshold = timedelta(days=7)
        self.warning_threshold = timedelta(days=30)
        
    def get_parks_freshness(self) -> pd.DataFrame:
        """
        Get data freshness for parks table.
        
        Returns:
            pd.DataFrame: Parks with collection dates and staleness status
        """
        query_path = os.path.join(
            os.path.dirname(__file__), 
            "..", 
            "queries", 
            "data_freshness", 
            "parks_staleness.sql"
        )
        
        with open(query_path, 'r') as f:
            query = f.read()
            
        return pd.read_sql(query, self.engine)
    
    def get_boundaries_freshness(self) -> pd.DataFrame:
        """
        Get data freshness for park_boundaries table.
        
        Returns:
            pd.DataFrame: Park boundaries with collection dates and staleness status
        """
        query_path = os.path.join(
            os.path.dirname(__file__), 
            "..", 
            "queries", 
            "data_freshness", 
            "boundaries_staleness.sql"
        )
        
        with open(query_path, 'r') as f:
            query = f.read()
            
        return pd.read_sql(query, self.engine)
    
    def get_osm_freshness(self) -> pd.DataFrame:
        """
        Get data freshness for OSM hikes table (park-level summary).
        
        Returns:
            pd.DataFrame: OSM data with most recent collection dates per park
        """
        try:
            query_path = os.path.join(
                os.path.dirname(__file__), 
                "..", 
                "queries", 
                "data_freshness", 
                "osm_staleness.sql"
            )
            
            with open(query_path, 'r') as f:
                query = f.read()
                
            return pd.read_sql(query, self.engine)
        except Exception as e:
            print(f"Warning: Could not query OSM hikes table: {e}")
            return pd.DataFrame()
    
    def get_tnm_freshness(self) -> pd.DataFrame:
        """
        Get data freshness for TNM hikes table (park-level summary).
        
        Returns:
            pd.DataFrame: TNM data with most recent collection dates per park
        """
        try:
            query_path = os.path.join(
                os.path.dirname(__file__), 
                "..", 
                "queries", 
                "data_freshness", 
                "tnm_staleness.sql"
            )
            
            with open(query_path, 'r') as f:
                query = f.read()
                
            return pd.read_sql(query, self.engine)
        except Exception as e:
            print(f"Warning: Could not query TNM hikes table: {e}")
            return pd.DataFrame()
    
    def get_freshness_summary(self) -> Dict[str, Dict]:
        """
        Get comprehensive freshness summary for all tables.
        
        Returns:
            Dict: Summary statistics for each table
        """
        summary = {}
        
        # Parks freshness
        parks_df = self.get_parks_freshness()
        summary['parks'] = {
            'total_parks': len(parks_df),
            'fresh_count': len(parks_df[parks_df['staleness_status'] == 'Fresh']),
            'warning_count': len(parks_df[parks_df['staleness_status'] == 'Warning']),
            'stale_count': len(parks_df[parks_df['staleness_status'] == 'Stale']),
            'oldest_data': parks_df['collected_at'].min() if not parks_df.empty else None,
            'newest_data': parks_df['collected_at'].max() if not parks_df.empty else None
        }
        
        # Boundaries freshness
        boundaries_df = self.get_boundaries_freshness()
        summary['boundaries'] = {
            'total_parks': len(boundaries_df),
            'fresh_count': len(boundaries_df[boundaries_df['staleness_status'] == 'Fresh']),
            'warning_count': len(boundaries_df[boundaries_df['staleness_status'] == 'Warning']),
            'stale_count': len(boundaries_df[boundaries_df['staleness_status'] == 'Stale']),
            'oldest_data': boundaries_df['collected_at'].min() if not boundaries_df.empty else None,
            'newest_data': boundaries_df['collected_at'].max() if not boundaries_df.empty else None
        }
        
        # OSM freshness
        osm_df = self.get_osm_freshness()
        summary['osm_hikes'] = {
            'total_parks': len(osm_df),
            'fresh_count': len(osm_df[osm_df['staleness_status'] == 'Fresh']) if not osm_df.empty else 0,
            'warning_count': len(osm_df[osm_df['staleness_status'] == 'Warning']) if not osm_df.empty else 0,
            'stale_count': len(osm_df[osm_df['staleness_status'] == 'Stale']) if not osm_df.empty else 0,
            'total_trails': osm_df['total_trails'].sum() if not osm_df.empty else 0,
            'oldest_data': osm_df['latest_trail_collected'].min() if not osm_df.empty else None,
            'newest_data': osm_df['latest_trail_collected'].max() if not osm_df.empty else None
        }
        
        # TNM freshness
        tnm_df = self.get_tnm_freshness()
        summary['tnm_hikes'] = {
            'total_parks': len(tnm_df),
            'fresh_count': len(tnm_df[tnm_df['staleness_status'] == 'Fresh']) if not tnm_df.empty else 0,
            'warning_count': len(tnm_df[tnm_df['staleness_status'] == 'Warning']) if not tnm_df.empty else 0,
            'stale_count': len(tnm_df[tnm_df['staleness_status'] == 'Stale']) if not tnm_df.empty else 0,
            'total_trails': tnm_df['total_trails'].sum() if not tnm_df.empty else 0,
            'oldest_data': tnm_df['latest_trail_collected'].min() if not tnm_df.empty else None,
            'newest_data': tnm_df['latest_trail_collected'].max() if not tnm_df.empty else None
        }
        
        return summary
    
    def print_freshness_report(self) -> None:
        """
        Print a comprehensive data freshness report.
        """
        print("=" * 80)
        print("DATA FRESHNESS MONITORING REPORT")
        print("=" * 80)
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Fresh threshold: {self.fresh_threshold.days} days")
        print(f"Warning threshold: {self.warning_threshold.days} days")
        print()
        
        # Get summary
        summary = self.get_freshness_summary()
        
        # Print summary for each table
        for table_name, stats in summary.items():
            print(f"{table_name.upper()} TABLE:")
            print(f"  Total parks: {stats['total_parks']}")
            print(f"  Fresh: {stats['fresh_count']} parks")
            print(f"  Warning: {stats['warning_count']} parks")
            print(f"  Stale: {stats['stale_count']} parks")
            
            if 'total_trails' in stats:
                print(f"  Total trails: {stats['total_trails']}")
            
            if stats['oldest_data']:
                print(f"  Oldest data: {stats['oldest_data']}")
            if stats['newest_data']:
                print(f"  Newest data: {stats['newest_data']}")
            
            print()
        
        # Print detailed tables
        print("DETAILED BREAKDOWN:")
        print("-" * 80)
        
        # Parks
        print("\nPARKS TABLE:")
        parks_df = self.get_parks_freshness()
        if not parks_df.empty:
            print(parks_df.to_string(index=False))
        else:
            print("No parks data found")
        
        # Boundaries
        print("\nPARK BOUNDARIES TABLE:")
        boundaries_df = self.get_boundaries_freshness()
        if not boundaries_df.empty:
            print(boundaries_df.to_string(index=False))
        else:
            print("No boundary data found")
        
        # OSM
        print("\nOSM HIKES TABLE (Park-Level Summary):")
        osm_df = self.get_osm_freshness()
        if not osm_df.empty:
            print(osm_df.to_string(index=False))
        else:
            print("No OSM data found")
        
        # TNM
        print("\nTNM HIKES TABLE (Park-Level Summary):")
        tnm_df = self.get_tnm_freshness()
        if not tnm_df.empty:
            print(tnm_df.to_string(index=False))
        else:
            print("No TNM data found")
        
        print("\n" + "=" * 80)


def run_data_freshness() -> Dict[str, Any]:
    """
    Run comprehensive data freshness monitoring.
    
    This function creates a monitor instance and generates a full report.
    
    Returns:
        Dict[str, Any]: Summary statistics from the monitoring
    """
    try:
        monitor = DataFreshnessMonitor()
        summary = monitor.get_freshness_summary()
        monitor.print_freshness_report()
        return summary
    except Exception as e:
        print(f"Error running data freshness monitoring: {e}")
        raise


def run_data_freshness_monitoring() -> None:
    """
    Run comprehensive data freshness monitoring.
    
    This function creates a monitor instance and generates a full report.
    """
    try:
        monitor = DataFreshnessMonitor()
        monitor.print_freshness_report()
    except Exception as e:
        print(f"Error running data freshness monitoring: {e}")
        raise


if __name__ == "__main__":
    run_data_freshness_monitoring() 
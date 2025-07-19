"""
Visualization profiling module.

This module creates visual representations of collected data
to validate spatial coverage and data quality.
"""
from ..utils import (
    get_db_connection, 
    ProfilingLogger
)
from ..config import PROFILING_MODULES, PROFILING_SETTINGS
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from sqlalchemy import text


class VisualizationProfiler:
    """Visualization profiling module."""
    
    def __init__(self):
        self.config = PROFILING_MODULES["visualization"]
        self.logger = ProfilingLogger("visualization")
        self.results = {}
    
    def run_park_map(self):
        """Create a map showing park locations and boundaries."""
        try:
            self.logger.info("Creating park map...")
            
            # Get park data from database
            engine = get_db_connection()
            
            # Query park points
            parks_query = """
            SELECT park_code, latitude, longitude, park_name
            FROM parks 
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
            """
            parks_df = pd.read_sql(parks_query, engine)
            
            # Query park boundaries
            boundaries_query = """
            SELECT p.park_code, geometry
            FROM parks p
            JOIN park_boundaries b ON p.park_code = b.park_code
            WHERE b.geometry IS NOT NULL
            """
            boundaries_gdf = gpd.read_postgis(boundaries_query, engine, geom_col='geometry')
            
            # Create the map
            self._create_park_map(parks_df, boundaries_gdf)
            
            self.logger.success("Park map")
            self.results["park_map"] = True
            
        except Exception as e:
            self.logger.error(f"Failed to create park map: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise
    
    def _create_park_map(self, parks_df, boundaries_gdf):
        """Create the actual map visualization."""
        # Create figure
        fig, ax = plt.subplots(1, 1, figsize=(20, 15))
        
        # Plot boundaries
        if not boundaries_gdf.empty:
            boundaries_gdf.plot(ax=ax, alpha=0.3, color='blue', edgecolor='blue')
        
        # Plot park points
        if not parks_df.empty:
            # Create GeoDataFrame for points
            from shapely.geometry import Point
            points_gdf = gpd.GeoDataFrame(
                parks_df,
                geometry=[Point(lon, lat) for lon, lat in zip(parks_df['longitude'], parks_df['latitude'])],
                crs="EPSG:4326"
            )
            points_gdf.plot(ax=ax, color='orange', markersize=20, alpha=0.7)
            
            # Add park name labels with leader lines
            self._add_park_labels(ax, parks_df)
        
        # Set up the map (no fixed ranges - let matplotlib auto-scale)
        ax.set_title("NPS Parks Data Collection Results", fontsize=16)
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        
        # Save the map
        output_path = f"{PROFILING_SETTINGS['output_directory']}/park_map.png"
        plt.savefig(output_path, dpi=400, bbox_inches='tight')
        plt.close()
        
        self.logger.info(f"Map saved to: {output_path}")
    
    def _add_park_labels(self, ax, parks_df):
        """Add park name labels with smart positioning to reduce overlap."""
        import numpy as np
        
        # Get current axis limits for positioning
        x_min, x_max = ax.get_xlim()
        y_min, y_max = ax.get_ylim()
        
        # Calculate base offset (small percentage of axis range)
        x_offset = (x_max - x_min) * 0.02
        y_offset = (y_max - y_min) * 0.02
        
        # Track placed label positions to avoid overlap
        placed_labels = []
        
        # Sort parks by latitude (north to south) to prioritize northern parks
        parks_df = parks_df.sort_values('latitude', ascending=False)
        
        for idx, row in parks_df.iterrows():
            lon, lat = row['longitude'], row['latitude']
            park_name = row['park_name']
            
            # Define multiple possible positions around the point
            positions = [
                (lon + x_offset, lat + y_offset),      # Right and up
                (lon - x_offset, lat + y_offset),      # Left and up
                (lon + x_offset, lat - y_offset),      # Right and down
                (lon - x_offset, lat - y_offset),      # Left and down
                (lon + x_offset * 1.5, lat),           # Further right
                (lon - x_offset * 1.5, lat),           # Further left
                (lon, lat + y_offset * 1.5),           # Further up
                (lon, lat - y_offset * 1.5),           # Further down
            ]
            
            # Find position with least overlap
            best_pos = positions[0]
            min_overlap = float('inf')
            
            for pos in positions:
                # Check overlap with already placed labels
                overlap_count = 0
                for placed in placed_labels:
                    # Calculate distance between positions
                    dist_x = abs(pos[0] - placed[0])
                    dist_y = abs(pos[1] - placed[1])
                    
                    # Consider it overlap if labels are too close
                    if dist_x < x_offset * 2 and dist_y < y_offset * 2:
                        overlap_count += 1
                
                if overlap_count < min_overlap:
                    min_overlap = overlap_count
                    best_pos = pos
            
            label_x, label_y = best_pos
            placed_labels.append((label_x, label_y))
            
            # Add leader line from point to label
            ax.plot([lon, label_x], [lat, label_y], 
                   color='black', linewidth=0.5, alpha=0.7)
            
            # Add label with white background for better readability
            ax.annotate(park_name, 
                       xy=(label_x, label_y),
                       xytext=(5, 5), textcoords='offset points',
                       fontsize=8, alpha=0.8,
                       bbox=dict(boxstyle='round,pad=0.3', 
                                facecolor='white', 
                                edgecolor='gray', 
                                alpha=0.7))
    
    def run_all(self):
        """Run all visualization queries."""
        for query_file in self.config["queries"]:
            query_name = query_file.replace('.sql', '')
            method_name = f"run_{query_name}"
            
            if hasattr(self, method_name):
                getattr(self, method_name)()
            else:
                self.logger.error(f"No method found for query: {query_name}")
        
        return self.results


# Convenience function
def run_visualization():
    """Convenience function to run visualization profiling."""
    profiler = VisualizationProfiler()
    return profiler.run_all()


if __name__ == "__main__":
    run_visualization() 
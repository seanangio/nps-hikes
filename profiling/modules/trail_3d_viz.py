#!/usr/bin/env python3
"""
Trail 3D Visualization Profiling Module

This module creates interactive 3D visualizations of trail elevation profiles
using Plotly. It allows users to explore trail geometry with elevation data
in an interactive 3D space.

Features:
- Interactive 3D trail visualization with rotation, zoom, pan
- Terrain-based color mapping (elevation gradient)
- Automatic CRS projection to local UTM zones
- Configurable Z-axis exaggeration
- Interactive CLI for trail selection
- Auto-opens visualization in browser

Usage:
    # Interactive mode - select park and trail
    python -m profiling.modules.trail_3d_viz

    # Direct mode - specify park and trail
    python -m profiling.modules.trail_3d_viz --park yell --trail "Mount Washburn Trail"

    # With custom z-axis scaling
    python -m profiling.modules.trail_3d_viz --park grca --trail "Bright Angel Trail" --z-scale 10
"""

import os
import sys
import re
import webbrowser
import argparse
from typing import Dict, List, Optional, Tuple
from sqlalchemy import text
import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString
import plotly.graph_objects as go
import numpy as np

from ..utils import (
    get_db_connection,
    ProfilingLogger,
)
from ..config import PROFILING_MODULES, PROFILING_SETTINGS


class Trail3DVisualizer:
    """Trail 3D visualization profiling module."""

    def __init__(self):
        self.config = PROFILING_MODULES.get("trail_3d_viz", {})
        self.logger = ProfilingLogger("trail_3d_viz")
        self.results = {}
        self.engine = get_db_connection()

        # Create output directory
        self.output_dir = (
            f"{PROFILING_SETTINGS['output_directory']}/visualizations/3d_trails"
        )
        os.makedirs(self.output_dir, exist_ok=True)

    def get_utm_crs(self, longitude: float, latitude: float) -> str:
        """
        Calculate appropriate UTM CRS for a given point.

        Args:
            longitude: Longitude in decimal degrees
            latitude: Latitude in decimal degrees

        Returns:
            EPSG code string (e.g., "EPSG:32612" for UTM Zone 12N)
        """
        utm_zone = int((longitude + 180) / 6) + 1
        hemisphere = "north" if latitude >= 0 else "south"
        epsg_code = 32600 + utm_zone if hemisphere == "north" else 32700 + utm_zone
        return f"EPSG:{epsg_code}"

    def sanitize_filename(self, name: str) -> str:
        """
        Sanitize trail name for use in filename.

        Removes/replaces special characters and spaces.

        Args:
            name: Original trail name

        Returns:
            Sanitized filename-safe string
        """
        # Convert to lowercase
        name = name.lower()
        # Replace spaces with underscores
        name = name.replace(" ", "_")
        # Remove special characters except underscores and hyphens
        name = re.sub(r"[^a-z0-9_-]", "", name)
        # Remove multiple underscores
        name = re.sub(r"_+", "_", name)
        # Remove leading/trailing underscores
        name = name.strip("_")
        return name

    def get_parks_with_trails(self) -> pd.DataFrame:
        """
        Get list of parks that have trails with elevation data.

        Returns:
            DataFrame with park_code, park_name, and trail_count
        """
        query = """
            SELECT
                ute.park_code,
                p.park_name,
                COUNT(*) as trail_count
            FROM usgs_trail_elevations ute
            JOIN parks p ON ute.park_code = p.park_code
            WHERE ute.collection_status IN ('COMPLETE', 'PARTIAL')
            GROUP BY ute.park_code, p.park_name
            ORDER BY p.park_name
        """

        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                df = pd.DataFrame(result.fetchall(), columns=result.keys())
                return df
        except Exception as e:
            self.logger.error(f"Failed to fetch parks: {e}")
            return pd.DataFrame()

    def get_trails_for_park(self, park_code: str) -> pd.DataFrame:
        """
        Get list of trails with elevation data for a specific park.

        Args:
            park_code: 4-character park code

        Returns:
            DataFrame with trail information
        """
        query = f"""
            SELECT
                trail_name,
                collection_status,
                total_points_count,
                CASE
                    WHEN collection_status = 'COMPLETE' THEN '✓'
                    WHEN collection_status = 'PARTIAL' THEN '⚠'
                    ELSE '✗'
                END as status_icon
            FROM usgs_trail_elevations
            WHERE park_code = '{park_code}'
            AND collection_status IN ('COMPLETE', 'PARTIAL')
            ORDER BY trail_name
        """

        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                df = pd.DataFrame(result.fetchall(), columns=result.keys())
                return df
        except Exception as e:
            self.logger.error(f"Failed to fetch trails for {park_code}: {e}")
            return pd.DataFrame()

    def fetch_trail_data(self, park_code: str, trail_name: str) -> Optional[Dict]:
        """
        Fetch trail elevation and geometry data from database.

        Args:
            park_code: 4-character park code
            trail_name: Name of the trail

        Returns:
            Dictionary with elevation_points list and metadata, or None if not found
        """
        query = f"""
            SELECT
                gmaps_location_id,
                trail_name,
                park_code,
                elevation_points,
                collection_status,
                total_points_count,
                failed_points_count
            FROM usgs_trail_elevations
            WHERE park_code = '{park_code}'
            AND trail_name = '{trail_name}'
            AND collection_status IN ('COMPLETE', 'PARTIAL')
        """

        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                row = result.fetchone()

                if not row:
                    self.logger.error(
                        f"No elevation data found for trail: {trail_name} in park: {park_code}"
                    )
                    return None

                # Extract data from row
                trail_data = {
                    "gmaps_location_id": row[0],
                    "trail_name": row[1],
                    "park_code": row[2],
                    "elevation_points": row[3],  # Already parsed as list by psycopg2
                    "collection_status": row[4],
                    "total_points_count": row[5],
                    "failed_points_count": row[6],
                }

                return trail_data

        except Exception as e:
            self.logger.error(f"Failed to fetch trail data: {e}")
            return None

    def calculate_trail_stats(self, elevation_points: List[Dict]) -> Dict:
        """
        Calculate trail statistics from elevation data.

        Args:
            elevation_points: List of elevation point dictionaries

        Returns:
            Dictionary with trail statistics
        """
        if not elevation_points:
            return {}

        elevations = [point["elevation_m"] for point in elevation_points]
        distances = [point["distance_m"] for point in elevation_points]

        # Calculate elevation gain/loss
        total_gain = sum(
            max(0, elevations[i + 1] - elevations[i])
            for i in range(len(elevations) - 1)
        )
        total_loss = sum(
            max(0, elevations[i] - elevations[i + 1])
            for i in range(len(elevations) - 1)
        )

        stats = {
            "total_distance_km": distances[-1] / 1000,
            "total_distance_mi": distances[-1] / 1609.34,
            "elevation_gain_m": total_gain,
            "elevation_gain_ft": total_gain * 3.28084,
            "elevation_loss_m": total_loss,
            "elevation_loss_ft": total_loss * 3.28084,
            "max_elevation_m": max(elevations),
            "max_elevation_ft": max(elevations) * 3.28084,
            "min_elevation_m": min(elevations),
            "min_elevation_ft": min(elevations) * 3.28084,
            "elevation_range_m": max(elevations) - min(elevations),
            "elevation_range_ft": (max(elevations) - min(elevations)) * 3.28084,
            "num_points": len(elevation_points),
        }

        return stats

    def create_3d_visualization(
        self,
        park_code: str,
        trail_name: str,
        z_exaggeration: float = 5.0,
    ) -> Optional[str]:
        """
        Create interactive 3D visualization of a trail.

        Args:
            park_code: 4-character park code
            trail_name: Name of the trail
            z_exaggeration: Z-axis scale factor (default 5.0)

        Returns:
            Path to generated HTML file, or None if failed
        """
        self.logger.info(f"Creating 3D visualization for: {trail_name} ({park_code})")

        # Fetch trail data
        trail_data = self.fetch_trail_data(park_code, trail_name)
        if not trail_data:
            return None

        elevation_points = trail_data["elevation_points"]
        if not elevation_points:
            self.logger.error("No elevation points found")
            return None

        # Calculate stats
        stats = self.calculate_trail_stats(elevation_points)

        # Display stats
        self.logger.info(f"Trail Statistics:")
        self.logger.info(
            f"  Distance: {stats['total_distance_mi']:.2f} mi ({stats['total_distance_km']:.2f} km)"
        )
        self.logger.info(
            f"  Elevation Gain: {stats['elevation_gain_ft']:.0f} ft ({stats['elevation_gain_m']:.0f} m)"
        )
        self.logger.info(
            f"  Elevation Loss: {stats['elevation_loss_ft']:.0f} ft ({stats['elevation_loss_m']:.0f} m)"
        )
        self.logger.info(
            f"  Elevation Range: {stats['elevation_range_ft']:.0f} ft ({stats['elevation_range_m']:.0f} m)"
        )
        self.logger.info(
            f"  Max Elevation: {stats['max_elevation_ft']:.0f} ft ({stats['max_elevation_m']:.0f} m)"
        )
        self.logger.info(
            f"  Min Elevation: {stats['min_elevation_ft']:.0f} ft ({stats['min_elevation_m']:.0f} m)"
        )
        self.logger.info(f"  Data Points: {stats['num_points']}")

        # Extract coordinates
        lats = [point["latitude"] for point in elevation_points]
        lons = [point["longitude"] for point in elevation_points]
        elevations = [point["elevation_m"] for point in elevation_points]

        # Calculate trail center for CRS
        center_lon = sum(lons) / len(lons)
        center_lat = sum(lats) / len(lats)

        # Get appropriate UTM CRS
        utm_crs = self.get_utm_crs(center_lon, center_lat)
        self.logger.info(f"Using CRS: {utm_crs}")

        # Convert to GeoDataFrame and project to UTM
        from shapely.geometry import Point

        geometry = [Point(lon, lat) for lon, lat in zip(lons, lats)]
        gdf = gpd.GeoDataFrame(
            {"elevation": elevations}, geometry=geometry, crs="EPSG:4326"
        )
        gdf_projected = gdf.to_crs(utm_crs)

        # Extract projected coordinates
        x_coords = [point.x for point in gdf_projected.geometry]
        y_coords = [point.y for point in gdf_projected.geometry]
        z_coords = [elev * z_exaggeration for elev in elevations]

        # Normalize coordinates to start at origin (for better visualization)
        x_coords = [x - min(x_coords) for x in x_coords]
        y_coords = [y - min(y_coords) for y in y_coords]

        # Create color scale based on elevation (terrain colors)
        # Normalize elevations to 0-1 range
        elev_min = min(elevations)
        elev_max = max(elevations)
        elev_range = elev_max - elev_min

        if elev_range > 0:
            normalized_elevations = [(e - elev_min) / elev_range for e in elevations]
        else:
            normalized_elevations = [0.5] * len(elevations)

        # Create 3D line plot
        fig = go.Figure()

        # Add the trail as a 3D line with color gradient
        fig.add_trace(
            go.Scatter3d(
                x=x_coords,
                y=y_coords,
                z=z_coords,
                mode="lines+markers",
                line=dict(
                    color=elevations,
                    colorscale="Earth",  # Classic terrain colors (green -> yellow -> brown -> white)
                    width=6,
                    colorbar=dict(
                        title="Elevation (m)",
                        x=1.1,
                    ),
                ),
                marker=dict(
                    size=2,
                    color=elevations,
                    colorscale="Earth",
                ),
                name=trail_name,
                hovertemplate=(
                    "<b>Distance</b>: %{text}<br>"
                    "<b>Elevation</b>: %{marker.color:.0f} m<br>"
                    "<b>X</b>: %{x:.0f} m<br>"
                    "<b>Y</b>: %{y:.0f} m<br>"
                    "<extra></extra>"
                ),
                text=[
                    f"{point['distance_m']/1000:.2f} km" for point in elevation_points
                ],
            )
        )

        # Update layout for better 3D visualization
        fig.update_layout(
            title=dict(
                text=f"{trail_name}<br><sub>{park_code.upper()} | "
                f"{stats['total_distance_mi']:.2f} mi | "
                f"+{stats['elevation_gain_ft']:.0f} ft / -{stats['elevation_loss_ft']:.0f} ft | "
                f"Z-scale: {z_exaggeration}x</sub>",
                x=0.5,
                xanchor="center",
            ),
            scene=dict(
                xaxis=dict(
                    title="Distance (m)",
                    backgroundcolor="rgb(240, 240, 240)",
                    gridcolor="white",
                    showbackground=True,
                ),
                yaxis=dict(
                    title="Distance (m)",
                    backgroundcolor="rgb(240, 240, 240)",
                    gridcolor="white",
                    showbackground=True,
                ),
                zaxis=dict(
                    title=f"Elevation (m, {z_exaggeration}x exaggeration)",
                    backgroundcolor="rgb(240, 240, 240)",
                    gridcolor="white",
                    showbackground=True,
                ),
                aspectmode="data",
                camera=dict(
                    eye=dict(x=1.5, y=1.5, z=1.2),
                    center=dict(x=0, y=0, z=0),
                ),
            ),
            showlegend=False,
            hovermode="closest",
            width=1200,
            height=800,
        )

        # Generate output filename
        sanitized_trail = self.sanitize_filename(trail_name)
        output_filename = f"{park_code}_{sanitized_trail}_3d.html"
        output_path = os.path.join(self.output_dir, output_filename)

        # Save to HTML
        fig.write_html(output_path)
        self.logger.success(f"Created 3D visualization: {output_path}")

        # Store result
        self.results[f"{park_code}_{trail_name}"] = output_path

        return output_path

    def interactive_selection(self, z_exaggeration: float = 5.0) -> Optional[str]:
        """
        Interactive CLI for selecting park and trail.

        Args:
            z_exaggeration: Z-axis scale factor

        Returns:
            Path to generated HTML file, or None if cancelled
        """
        # Get parks
        parks_df = self.get_parks_with_trails()
        if parks_df.empty:
            self.logger.error("No parks with elevation data found")
            return None

        # Display parks
        print("\n" + "=" * 70)
        print("AVAILABLE PARKS WITH ELEVATION DATA")
        print("=" * 70)
        for idx, row in parks_df.iterrows():
            print(
                f"{idx + 1:2d}. {row['park_name']:40s} ({row['park_code']}) - {row['trail_count']} trails"
            )
        print("=" * 70)

        # Select park
        while True:
            try:
                park_choice = input("\nSelect park number (or 'q' to quit): ").strip()
                if park_choice.lower() == "q":
                    return None
                park_idx = int(park_choice) - 1
                if 0 <= park_idx < len(parks_df):
                    break
                print(f"Please enter a number between 1 and {len(parks_df)}")
            except (ValueError, KeyboardInterrupt):
                print("\nCancelled")
                return None

        selected_park = parks_df.iloc[park_idx]
        park_code = selected_park["park_code"]
        park_name = selected_park["park_name"]

        # Get trails for selected park
        trails_df = self.get_trails_for_park(park_code)
        if trails_df.empty:
            self.logger.error(f"No trails found for {park_name}")
            return None

        # Display trails
        print("\n" + "=" * 70)
        print(f"AVAILABLE TRAILS FOR {park_name.upper()} ({park_code.upper()})")
        print("=" * 70)
        for idx, row in trails_df.iterrows():
            status_icon = row["status_icon"]
            trail_name = row["trail_name"]
            points = row["total_points_count"]
            print(f"{idx + 1:2d}. {status_icon} {trail_name:50s} ({points} points)")
        print("=" * 70)

        # Select trail
        while True:
            try:
                trail_choice = input("\nSelect trail number (or 'q' to quit): ").strip()
                if trail_choice.lower() == "q":
                    return None
                trail_idx = int(trail_choice) - 1
                if 0 <= trail_idx < len(trails_df):
                    break
                print(f"Please enter a number between 1 and {len(trails_df)}")
            except (ValueError, KeyboardInterrupt):
                print("\nCancelled")
                return None

        selected_trail = trails_df.iloc[trail_idx]
        trail_name = selected_trail["trail_name"]

        # Ask about z-exaggeration
        print(f"\nCurrent Z-axis exaggeration: {z_exaggeration}x")
        adjust = input("Adjust Z-axis exaggeration? (y/N): ").strip().lower()
        if adjust == "y":
            while True:
                try:
                    new_z = input(
                        f"Enter Z-axis exaggeration factor (current: {z_exaggeration}): "
                    ).strip()
                    z_exaggeration = float(new_z)
                    if z_exaggeration > 0:
                        break
                    print("Z-exaggeration must be positive")
                except ValueError:
                    print("Please enter a valid number")

        # Create visualization
        print()
        return self.create_3d_visualization(park_code, trail_name, z_exaggeration)

    def run_all(
        self,
        park_code: str | None = None,
        trail_name: str | None = None,
        z_exaggeration: float = 5.0,
    ):
        """
        Run 3D visualization profiling.

        Args:
            park_code: Optional park code for direct mode
            trail_name: Optional trail name for direct mode
            z_exaggeration: Z-axis scale factor

        Returns:
            Dictionary with results
        """
        if park_code and trail_name:
            # Direct mode
            output_path = self.create_3d_visualization(
                park_code, trail_name, z_exaggeration
            )
            if output_path:
                return {"output_path": output_path, "mode": "direct"}
            return {"error": "Failed to create visualization", "mode": "direct"}
        else:
            # Interactive mode
            output_path = self.interactive_selection(z_exaggeration)
            if output_path:
                return {"output_path": output_path, "mode": "interactive"}
            return {"cancelled": True, "mode": "interactive"}


# Convenience function
def run_trail_3d_viz(
    park_code: str | None = None,
    trail_name: str | None = None,
    z_exaggeration: float = 5.0,
):
    """Convenience function to run trail 3D visualization profiling."""
    visualizer = Trail3DVisualizer()
    return visualizer.run_all(park_code, trail_name, z_exaggeration)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Create interactive 3D visualizations of trail elevation profiles"
    )
    parser.add_argument(
        "--park",
        type=str,
        help="Park code (e.g., yell, grca)",
    )
    parser.add_argument(
        "--trail",
        type=str,
        help='Trail name (e.g., "Mount Washburn Trail")',
    )
    parser.add_argument(
        "--z-scale",
        type=float,
        default=5.0,
        help="Z-axis exaggeration factor (default: 5.0)",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Do not automatically open the visualization in browser",
    )

    args = parser.parse_args()

    # Create visualizer
    visualizer = Trail3DVisualizer()

    # Run visualization
    if args.park and args.trail:
        # Direct mode
        result = visualizer.run_all(args.park, args.trail, args.z_scale)
    else:
        # Interactive mode
        result = visualizer.run_all(z_exaggeration=args.z_scale)

    # Open in browser if successful
    if result and "output_path" in result and not args.no_open:
        output_path = result["output_path"]
        print(f"\nOpening visualization in browser...")
        webbrowser.open(f"file://{os.path.abspath(output_path)}")

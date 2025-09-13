"""
Enhanced visualization profiling module.

This module creates both static and interactive visualizations of collected data
to validate spatial coverage and data quality.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables before importing config-dependent modules
load_dotenv()

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from ..utils import get_db_connection, ProfilingLogger
from ..config import PROFILING_MODULES, PROFILING_SETTINGS
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from sqlalchemy import text
import folium
from shapely.geometry import Point, box
from shapely import wkb


class VisualizationProfiler:
    """Enhanced visualization profiling module."""

    def __init__(self):
        self.config = PROFILING_MODULES["visualization"]
        self.logger = ProfilingLogger("visualization")
        self.results = {}

        # Create output directories with better organization
        self.static_dir = f"{PROFILING_SETTINGS['output_directory']}/static_maps"
        self.interactive_dir = (
            f"{PROFILING_SETTINGS['output_directory']}/interactive_maps"
        )
        os.makedirs(self.static_dir, exist_ok=True)
        os.makedirs(self.interactive_dir, exist_ok=True)

    def run_individual_park_maps(self):
        """Create static maps for each individual park."""
        try:
            self.logger.info("Creating individual park maps...")

            engine = get_db_connection()

            # Get all parks with boundaries
            parks_query = """
            SELECT DISTINCT p.park_code, p.park_name, p.latitude, p.longitude,
                   b.geometry as boundary_geom, b.bbox
            FROM parks p
            JOIN park_boundaries b ON p.park_code = b.park_code
            WHERE b.geometry IS NOT NULL
            ORDER BY p.park_code
            """

            parks_df = pd.read_sql(parks_query, engine)

            created_maps = 0
            for _, park in parks_df.iterrows():
                try:
                    self._create_individual_park_map(engine, park)
                    created_maps += 1
                except Exception as e:
                    self.logger.error(
                        f"Failed to create map for {park['park_code']}: {e}"
                    )
                    continue

            self.logger.success(f"Created {created_maps} individual park maps")
            self.results["individual_park_maps"] = created_maps

        except Exception as e:
            self.logger.error(f"Failed to create individual park maps: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise

    def _create_individual_park_map(self, engine, park):
        """Create a static map for a single park."""
        park_code = park["park_code"]
        park_name = park["park_name"]

        # Get OSM trails for this park - use f-string instead of params
        osm_query = f"""
        SELECT name, length_mi, geometry
        FROM osm_hikes 
        WHERE park_code = '{park_code}'
        """
        osm_trails = gpd.read_postgis(osm_query, engine, geom_col="geometry")

        # Get TNM trails for this park - use f-string instead of params
        tnm_query = f"""
        SELECT name, lengthmiles as length_mi, geometry
        FROM tnm_hikes 
        WHERE park_code = '{park_code}'
        """
        tnm_trails = gpd.read_postgis(tnm_query, engine, geom_col="geometry")

        # Get GMaps locations for this park
        gmaps_query = f"""
        SELECT location_name as name, longitude as lon, latitude as lat
        FROM gmaps_hiking_locations 
        WHERE park_code = '{park_code}'
        """
        gmaps_locations = pd.read_sql(gmaps_query, engine)

        # Create the map with better color scheme
        fig, ax = plt.subplots(1, 1, figsize=(12, 10))

        # Set background color to light gray for better contrast
        ax.set_facecolor("#f8f9fa")

        # Plot park boundary - handle WKB geometry properly
        if park["boundary_geom"]:
            try:
                # Convert WKB string to Shapely geometry
                boundary_geom = wkb.loads(park["boundary_geom"], hex=True)
                boundary_data = [{"geometry": boundary_geom}]
                boundary_gdf = gpd.GeoDataFrame(boundary_data, crs="EPSG:4326")
                # Use dark green for park boundaries (distinct from blue trails)
                boundary_gdf.plot(
                    ax=ax, color="#e8f5e8", edgecolor="#2d5016", linewidth=2, alpha=0.8
                )
            except Exception as e:
                self.logger.debug(f"Could not plot boundary for {park_code}: {e}")

        # Plot bounding box if available
        if park["bbox"]:
            try:
                bbox_coords = [float(x) for x in park["bbox"].split(",")]
                bbox_geom = box(
                    bbox_coords[0], bbox_coords[1], bbox_coords[2], bbox_coords[3]
                )
                bbox_data = [{"geometry": bbox_geom}]
                bbox_gdf = gpd.GeoDataFrame(bbox_data, crs="EPSG:4326")
                bbox_gdf.plot(
                    ax=ax,
                    color="none",
                    edgecolor="#dc3545",
                    linewidth=2,
                    linestyle="--",
                    alpha=0.8,
                )
            except Exception as e:
                self.logger.debug(f"Could not plot bbox for {park_code}: {e}")

        # Plot center point - make it smaller
        if park["latitude"] and park["longitude"]:
            center_point = Point(park["longitude"], park["latitude"])
            center_data = [{"geometry": center_point}]
            center_gdf = gpd.GeoDataFrame(center_data, crs="EPSG:4326")
            center_gdf.plot(ax=ax, color="#dc3545", markersize=30, alpha=0.8)

        # Calculate trail statistics for legend
        osm_count = len(osm_trails)
        tnm_count = len(tnm_trails)
        gmaps_count = len(gmaps_locations)
        osm_length = osm_trails["length_mi"].sum() if not osm_trails.empty else 0
        tnm_length = tnm_trails["length_mi"].sum() if not tnm_trails.empty else 0

        # Plot OSM trails with blue color and reduced opacity for better overlap visibility
        if not osm_trails.empty:
            osm_trails.plot(
                ax=ax,
                color="#007bff",
                linewidth=1.5,
                alpha=0.7,
                label=f"OSM: {osm_count} trails, {osm_length:.1f} mi",
            )

        # Plot TNM trails with orange color and reduced opacity for better overlap visibility
        if not tnm_trails.empty:
            tnm_trails.plot(
                ax=ax,
                color="#fd7e14",
                linewidth=1.5,
                alpha=0.7,
                label=f"TNM: {tnm_count} trails, {tnm_length:.1f} mi",
            )

        # Plot GMaps locations with purple color
        if not gmaps_locations.empty:
            ax.scatter(
                gmaps_locations["lon"],
                gmaps_locations["lat"],
                color="#6f42c1",
                s=20,
                alpha=0.8,
                label=f"GMap: {gmaps_count} points",
            )

            # Add smart labels
            self._add_smart_labels(ax, gmaps_locations, boundary_geom)

        # Set up the map
        ax.set_title(
            f"{park_name} ({park_code.upper()})", fontsize=16, fontweight="bold"
        )
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")

        # Add consolidated legend in top right only
        if not osm_trails.empty or not tnm_trails.empty or not gmaps_locations.empty:
            ax.legend(loc="upper right", framealpha=0.9, fancybox=True, shadow=True)

        # Save the map
        output_path = f"{self.static_dir}/{park_code}_trails.png"
        plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
        plt.close()

        self.logger.info(f"Created map for {park_code}: {output_path}")

    def _plot_gmaps_locations(self, ax, gmaps_locations, park_boundary):
        """Plot GMaps locations with smart label positioning."""
        if gmaps_locations.empty:
            return 0

        # Plot GMaps points
        gmaps_locations.plot(
            ax=ax,
            color="#6f42c1",
            markersize=20,
            alpha=0.8,
            label=f"GMap: {len(gmaps_locations)} points",
        )

        # Add labels with smart positioning
        self._add_smart_labels(ax, gmaps_locations, park_boundary)

        return len(gmaps_locations)

    def _add_smart_labels(self, ax, gmaps_locations, park_boundary):
        """Add smart labels to GMaps locations to avoid overlaps."""
        if gmaps_locations.empty:
            return

        # Get park boundary bounds for label positioning
        if park_boundary is not None:
            bounds = park_boundary.bounds
            park_width = bounds[2] - bounds[0]
            park_height = bounds[3] - bounds[1]
        else:
            # Fallback to data bounds
            min_lon = gmaps_locations["lon"].min()
            max_lon = gmaps_locations["lon"].max()
            min_lat = gmaps_locations["lat"].min()
            max_lat = gmaps_locations["lat"].max()
            park_width = max_lon - min_lon
            park_height = max_lat - min_lat

        # Calculate label offset based on park size
        label_offset = max(park_width, park_height) * 0.02

        # Track used positions to avoid overlaps
        used_positions = []

        for idx, location in gmaps_locations.iterrows():
            name = location["name"] or "Unnamed"
            lon = location["lon"]
            lat = location["lat"]

            # Try different label positions to avoid overlaps
            label_positions = [
                (lon, lat + label_offset),  # Above
                (lon + label_offset, lat),  # Right
                (lon, lat - label_offset),  # Below
                (lon - label_offset, lat),  # Left
                (lon + label_offset, lat + label_offset),  # Top-right
                (lon - label_offset, lat + label_offset),  # Top-left
                (lon + label_offset, lat - label_offset),  # Bottom-right
                (lon - label_offset, lat - label_offset),  # Bottom-left
            ]

            # Find best position that doesn't overlap
            best_position = None
            for pos in label_positions:
                if not self._position_overlaps(pos, used_positions, label_offset):
                    best_position = pos
                    break

            if best_position is None:
                # If all positions overlap, use the first one
                best_position = label_positions[0]

            # Add to used positions
            used_positions.append(best_position)

            # Draw line from point to label
            ax.plot(
                [lon, best_position[0]],
                [lat, best_position[1]],
                color="#6f42c1",
                linewidth=0.8,
                alpha=0.6,
            )

            # Add label with background box
            ax.annotate(
                name,
                xy=best_position,
                xytext=best_position,
                ha="center",
                va="center",
                fontsize=8,
                fontweight="bold",
                bbox=dict(
                    boxstyle="round,pad=0.3",
                    facecolor="white",
                    edgecolor="#6f42c1",
                    alpha=0.8,
                    linewidth=0.5,
                ),
            )

    def _position_overlaps(self, pos, used_positions, min_distance):
        """Check if a position overlaps with existing positions."""
        for used_pos in used_positions:
            distance = (
                (pos[0] - used_pos[0]) ** 2 + (pos[1] - used_pos[1]) ** 2
            ) ** 0.5
            if distance < min_distance:
                return True
        return False

    def run_interactive_map(self):
        """Create one comprehensive interactive map with all parks and trails."""
        try:
            self.logger.info("Creating comprehensive interactive map...")

            engine = get_db_connection()

            # Get all parks with boundaries
            parks_query = """
            SELECT p.park_code, p.park_name, p.latitude, p.longitude,
                   b.geometry as boundary_geom
            FROM parks p
            JOIN park_boundaries b ON p.park_code = b.park_code
            WHERE b.geometry IS NOT NULL AND p.latitude IS NOT NULL
            """
            parks_df = pd.read_sql(parks_query, engine)

            # Get all OSM trails
            osm_query = """
            SELECT park_code, name, length_mi, geometry
            FROM osm_hikes
            """
            osm_trails = gpd.read_postgis(osm_query, engine, geom_col="geometry")

            # Get all TNM trails
            tnm_query = """
            SELECT park_code, name, lengthmiles as length_mi, geometry
            FROM tnm_hikes
            """
            tnm_trails = gpd.read_postgis(tnm_query, engine, geom_col="geometry")

            # Create the interactive map
            self._create_interactive_map(parks_df, osm_trails, tnm_trails)

            self.logger.success("Interactive map created successfully")
            self.results["interactive_map"] = True

        except Exception as e:
            self.logger.error(f"Failed to create interactive map: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise

    def run_test_interactive_map(self):
        """Create a test interactive map with just a few parks to verify functionality."""
        try:
            self.logger.info("Creating test interactive map...")

            engine = get_db_connection()

            # Get just a few parks for testing
            parks_query = """
            SELECT p.park_code, p.park_name, p.latitude, p.longitude,
                   b.geometry as boundary_geom
            FROM parks p
            JOIN park_boundaries b ON p.park_code = b.park_code
            WHERE b.geometry IS NOT NULL AND p.latitude IS NOT NULL
            LIMIT 5
            """
            parks_df = pd.read_sql(parks_query, engine)

            # Get OSM trails for these parks
            park_codes = "', '".join(parks_df["park_code"].tolist())
            osm_query = f"""
            SELECT park_code, name, length_mi, geometry
            FROM osm_hikes
            WHERE park_code IN ('{park_codes}')
            LIMIT 50
            """
            osm_trails = gpd.read_postgis(osm_query, engine, geom_col="geometry")

            # Get TNM trails for these parks
            tnm_query = f"""
            SELECT park_code, name, lengthmiles as length_mi, geometry
            FROM tnm_hikes
            WHERE park_code IN ('{park_codes}')
            LIMIT 50
            """
            tnm_trails = gpd.read_postgis(tnm_query, engine, geom_col="geometry")

            # Create the test interactive map
            self._create_interactive_map(parks_df, osm_trails, tnm_trails, is_test=True)

            self.logger.success("Test interactive map created successfully")
            self.results["test_interactive_map"] = True

        except Exception as e:
            self.logger.error(f"Failed to create test interactive map: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise

    def _create_interactive_map(self, parks_df, osm_trails, tnm_trails, is_test=False):
        """Create the comprehensive interactive map."""
        # Calculate center point for map initialization
        center_lat = parks_df["latitude"].mean()
        center_lon = parks_df["longitude"].mean()

        self.logger.info(
            f"Creating interactive map centered at: {center_lat:.4f}, {center_lon:.4f}"
        )
        self.logger.info(
            f"Found {len(parks_df)} parks, {len(osm_trails)} OSM trails, {len(tnm_trails)} TNM trails"
        )

        # Create base map with better tile layer
        zoom_level = 8 if is_test else 6  # Higher zoom for test map
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=zoom_level,  # Increased zoom level to make trails more visible
            tiles="CartoDB positron",  # Better background for trail visibility
        )

        # Add layer control
        folium.LayerControl().add_to(m)

        # Create feature groups for different layers
        park_boundaries_fg = folium.FeatureGroup(name="Park Boundaries", show=True)
        osm_trails_fg = folium.FeatureGroup(name="OSM Trails", show=True)
        tnm_trails_fg = folium.FeatureGroup(name="TNM Trails", show=True)

        # Add park boundaries with better styling
        boundary_count = 0
        for _, park in parks_df.iterrows():
            if park["boundary_geom"]:
                try:
                    # Convert WKB string to Shapely geometry
                    boundary_geom = wkb.loads(park["boundary_geom"], hex=True)
                    boundary_data = [{"geometry": boundary_geom}]
                    boundary_gdf = gpd.GeoDataFrame(boundary_data, crs="EPSG:4326")

                    folium.GeoJson(
                        boundary_gdf,
                        name=f"{park['park_name']} Boundary",
                        style_function=lambda x: {
                            "fillColor": "#e8f5e8",
                            "color": "#2d5016",
                            "weight": 1.5,
                            "fillOpacity": 0.3,
                        },
                        popup=folium.Popup(
                            f"<b>{park['park_name']}</b><br>Code: {park['park_code'].upper()}"
                        ),
                    ).add_to(park_boundaries_fg)
                    boundary_count += 1
                except Exception as e:
                    self.logger.debug(
                        f"Could not add boundary for {park['park_code']}: {e}"
                    )

        # Add OSM trails with better styling
        osm_count = 0
        for _, trail in osm_trails.iterrows():
            try:
                trail_data = [{"geometry": trail["geometry"]}]
                trail_gdf = gpd.GeoDataFrame(trail_data, crs="EPSG:4326")

                folium.GeoJson(
                    trail_gdf,
                    style_function=lambda x: {
                        "color": "#007bff",
                        "weight": 1.5,
                        "opacity": 0.7,
                    },
                    popup=folium.Popup(
                        f"<b>OSM Trail</b><br>"
                        f"Name: {trail['name'] or 'Unnamed'}<br>"
                        f"Length: {trail['length_mi']:.2f} mi<br>"
                        f"Park: {trail['park_code'].upper()}"
                    ),
                ).add_to(osm_trails_fg)
                osm_count += 1
            except Exception as e:
                self.logger.debug(f"Could not add OSM trail: {e}")

        # Add TNM trails with better styling
        tnm_count = 0
        for _, trail in tnm_trails.iterrows():
            try:
                trail_data = [{"geometry": trail["geometry"]}]
                trail_gdf = gpd.GeoDataFrame(trail_data, crs="EPSG:4326")

                folium.GeoJson(
                    trail_gdf,
                    style_function=lambda x: {
                        "color": "#fd7e14",
                        "weight": 1.5,
                        "opacity": 0.7,
                    },
                    popup=folium.Popup(
                        f"<b>TNM Trail</b><br>"
                        f"Name: {trail['name'] or 'Unnamed'}<br>"
                        f"Length: {trail['length_mi']:.2f} mi<br>"
                        f"Park: {trail['park_code'].upper()}"
                    ),
                ).add_to(tnm_trails_fg)
                tnm_count += 1
            except Exception as e:
                self.logger.debug(f"Could not add TNM trail: {e}")

        self.logger.info(
            f"Added {boundary_count} boundaries, {osm_count} OSM trails, {tnm_count} TNM trails to map"
        )

        # Add all feature groups to map
        park_boundaries_fg.add_to(m)
        osm_trails_fg.add_to(m)
        tnm_trails_fg.add_to(m)

        # Save the map
        suffix = "_test" if is_test else ""
        output_path = f"{self.interactive_dir}/trails_map{suffix}.html"
        m.save(output_path)

        self.logger.info(f"Interactive map saved to: {output_path}")

    def run_all(self):
        """Run all visualization methods."""
        self.run_individual_park_maps()
        self.run_interactive_map()
        self.run_test_interactive_map()  # Add test map for debugging
        return self.results


# Convenience function
def run_visualization():
    """Convenience function to run visualization profiling."""
    profiler = VisualizationProfiler()
    return profiler.run_all()


if __name__ == "__main__":
    run_visualization()

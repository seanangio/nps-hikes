"""
US Park Map visualization module.

Creates two complementary views of all national parks:
1. Static PNG — Albers Equal Area projection with AK/HI insets (geopandas + matplotlib)
2. Interactive HTML — zoomable map with park boundaries and hover tooltips (Plotly)

Parks are color-coded by visited/unvisited status, with a visit count in the legend.

Usage:
    # Via orchestrator
    python profiling/orchestrator.py us_park_map

    # Standalone
    python -m profiling.modules.us_park_map
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import cartopy.io.shapereader as shpreader
import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
import plotly.graph_objects as go
from adjustText import adjust_text
from shapely.geometry import Point

from ..config import PROFILING_MODULES, PROFILING_SETTINGS
from ..utils import ProfilingLogger, get_db_connection

# Colors
VISITED_COLOR = "#2d6a4f"
UNVISITED_COLOR = "#aaaaaa"
VISITED_MARKER_SIZE = 40
UNVISITED_MARKER_SIZE = 24

# CRS definitions (EPSG codes for Albers projections)
CONUS_CRS = "+proj=aea +lat_1=29.5 +lat_2=45.5 +lat_0=37.5 +lon_0=-96 +datum=NAD83"
AK_CRS = "+proj=aea +lat_1=55 +lat_2=65 +lat_0=50 +lon_0=-154 +datum=NAD83"
HI_CRS = "+proj=aea +lat_1=19 +lat_2=22 +lat_0=20.5 +lon_0=-157 +datum=NAD83"


class USParkMapProfiler:
    """US overview map showing visited and unvisited national parks."""

    def __init__(self):
        self.config = PROFILING_MODULES["us_park_map"]
        self.logger = ProfilingLogger("us_park_map")
        self.results = {}

        self.output_dir = (
            f"{PROFILING_SETTINGS['output_directory']}/visualizations/us_park_map"
        )
        os.makedirs(self.output_dir, exist_ok=True)

    def _fetch_parks(self):
        """Fetch all parks with coordinates and visit status."""
        engine = get_db_connection()
        query = """
        SELECT park_code, park_name, latitude, longitude,
               states, visit_month, visit_year
        FROM parks
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        ORDER BY park_name
        """
        df = pd.read_sql(query, engine)
        df["visited"] = df["visit_year"].notna()
        return df

    def _fetch_boundaries(self):
        """Fetch park boundary geometries for the interactive map."""
        engine = get_db_connection()
        query = """
        SELECT pb.park_code, pb.geometry
        FROM park_boundaries pb
        JOIN parks p ON pb.park_code = p.park_code
        WHERE pb.geometry IS NOT NULL
        """
        return gpd.read_postgis(query, engine, geom_col="geometry")

    def _load_us_states_gdf(self):
        """Load US state geometries as a GeoDataFrame in WGS84."""
        shpfilename = shpreader.natural_earth(
            resolution="50m",
            category="cultural",
            name="admin_1_states_provinces_lakes",
        )
        all_states = gpd.read_file(shpfilename)
        us = all_states[all_states["admin"] == "United States of America"].copy()
        return us

    def _parks_to_gdf(self, parks_df):
        """Convert parks DataFrame to a GeoDataFrame in WGS84."""
        geometry = [
            Point(row["longitude"], row["latitude"]) for _, row in parks_df.iterrows()
        ]
        return gpd.GeoDataFrame(parks_df, geometry=geometry, crs="EPSG:4326")

    # ------------------------------------------------------------------ #
    #  Static map (geopandas + matplotlib)
    # ------------------------------------------------------------------ #

    def run_static_map(self, parks_df):
        """Create a static US map with AK/HI insets using geopandas."""
        try:
            self.logger.info("Creating static US park map...")

            us_gdf = self._load_us_states_gdf()
            parks_gdf = self._parks_to_gdf(parks_df)

            # Split states by region
            conus_gdf = us_gdf[~us_gdf["name"].isin(["Alaska", "Hawaii"])]
            # Filter to actual CONUS (exclude overseas territories)
            rep_pts = conus_gdf.geometry.representative_point()
            conus_gdf = conus_gdf[
                rep_pts.y.between(24, 50) & rep_pts.x.between(-130, -60)
            ]
            ak_gdf = us_gdf[us_gdf["name"] == "Alaska"]
            hi_gdf = us_gdf[us_gdf["name"] == "Hawaii"]

            # Split parks by region (filter by coordinates to exclude territories)
            conus_parks = parks_gdf[
                parks_gdf["latitude"].between(24, 50)
                & parks_gdf["longitude"].between(-130, -60)
            ]
            ak_parks = parks_gdf[parks_gdf["states"].str.contains("AK", na=False)]
            hi_parks = parks_gdf[parks_gdf["states"].str.contains("HI", na=False)]

            # Reproject everything
            conus_states_proj = conus_gdf.to_crs(CONUS_CRS)
            conus_parks_proj = conus_parks.to_crs(CONUS_CRS)
            ak_states_proj = ak_gdf.to_crs(AK_CRS)
            ak_parks_proj = ak_parks.to_crs(AK_CRS)
            hi_states_proj = hi_gdf.to_crs(HI_CRS)
            hi_parks_proj = hi_parks.to_crs(HI_CRS)

            # Create figure — wide aspect ratio for a landscape map
            fig = plt.figure(figsize=(18, 9))
            fig.suptitle(
                "US National Park Visits",
                fontsize=20,
                fontweight="bold",
                y=0.99,
            )

            # --- CONUS (main axes) ---
            ax_main = fig.add_axes([0.0, 0.0, 1.0, 0.95])
            self._plot_panel(ax_main, conus_states_proj, conus_parks_proj)

            # --- Alaska inset (overlaps bottom-left of CONUS) ---
            ax_ak = fig.add_axes([0.0, 0.0, 0.24, 0.24])
            self._plot_panel(ax_ak, ak_states_proj, ak_parks_proj)
            self._add_inset_border(ax_ak)

            # --- Hawaii inset (right of Alaska, tight fit) ---
            ax_hi = fig.add_axes([0.23, 0.0, 0.12, 0.15])
            self._plot_panel(ax_hi, hi_states_proj, hi_parks_proj)
            self._add_inset_border(ax_hi)
            # Tighten Hawaii xlim to remove left-side padding
            hi_bounds = hi_states_proj.total_bounds  # [minx, miny, maxx, maxy]
            pad = (hi_bounds[2] - hi_bounds[0]) * 0.05
            ax_hi.set_xlim(hi_bounds[0] - pad, hi_bounds[2] + pad)

            # Combined legend with counts on CONUS axes
            visited_count = int(parks_df["visited"].sum())
            unvisited_count = len(parks_df) - visited_count
            from matplotlib.lines import Line2D

            legend_elements = [
                Line2D(
                    [0],
                    [0],
                    marker="o",
                    color="w",
                    markerfacecolor=VISITED_COLOR,
                    markersize=10,
                    label=f"Visited ({visited_count})",
                ),
                Line2D(
                    [0],
                    [0],
                    marker="o",
                    color="w",
                    markerfacecolor=UNVISITED_COLOR,
                    markersize=8,
                    label=f"Not visited ({unvisited_count})",
                ),
            ]
            ax_main.legend(
                handles=legend_elements,
                loc="lower right",
                framealpha=0.9,
                fontsize=11,
                edgecolor="#cccccc",
            )

            output_path = os.path.join(self.output_dir, "us_park_map_static.png")
            plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
            plt.close()

            self.logger.success(f"Static map saved: {output_path}")
            self.results["static_map"] = output_path

        except Exception as e:
            self.logger.error(f"Failed to create static map: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise

    def _add_inset_border(self, ax):
        """Draw a thin border around an inset axes to separate from CONUS."""
        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_edgecolor("#cccccc")
            spine.set_linewidth(0.8)

    def _plot_panel(self, ax, states_proj, parks_proj):
        """Plot states and parks on a plain matplotlib axes."""
        # Draw states
        states_proj.plot(
            ax=ax,
            facecolor="#f0f0ec",
            edgecolor="#999999",
            linewidth=0.4,
        )

        # Draw parks
        visited = parks_proj[parks_proj["visited"]]
        unvisited = parks_proj[~parks_proj["visited"]]

        if not unvisited.empty:
            unvisited.plot(
                ax=ax,
                color=UNVISITED_COLOR,
                edgecolor="#888888",
                linewidth=0.5,
                markersize=UNVISITED_MARKER_SIZE,
                zorder=5,
            )
        if not visited.empty:
            visited.plot(
                ax=ax,
                color=VISITED_COLOR,
                edgecolor="#1b4332",
                linewidth=0.5,
                markersize=VISITED_MARKER_SIZE,
                zorder=6,
            )

        # Labels with color matching visit status
        if not parks_proj.empty:
            xs = parks_proj.geometry.x.tolist()
            ys = parks_proj.geometry.y.tolist()
            texts = []
            for (_, park), x, y in zip(parks_proj.iterrows(), xs, ys, strict=True):
                color = VISITED_COLOR if park["visited"] else UNVISITED_COLOR
                t = ax.text(
                    x,
                    y,
                    park["park_name"],
                    fontsize=5.5,
                    fontweight="bold",
                    color=color,
                    ha="center",
                    va="bottom",
                    zorder=7,
                )
                texts.append(t)

            # Let adjustText reposition labels (no arrows yet)
            adjust_text(
                texts,
                x=xs,
                y=ys,
                ax=ax,
                expand=(1.2, 1.4),
                force_text=(0.3, 0.5),
                force_points=(0.4, 0.6),
            )

            # Draw connector lines only where the label moved significantly
            xlim = ax.get_xlim()
            data_range = xlim[1] - xlim[0]
            min_arrow_dist = data_range * 0.025  # ~2.5% of map width

            for t, orig_x, orig_y in zip(texts, xs, ys, strict=True):
                txt_x, txt_y = t.get_position()
                dist = ((txt_x - orig_x) ** 2 + (txt_y - orig_y) ** 2) ** 0.5
                if dist > min_arrow_dist:
                    ax.plot(
                        [orig_x, txt_x],
                        [orig_y, txt_y],
                        color="#888888",
                        linewidth=0.4,
                        zorder=3,
                    )

        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)

    # ------------------------------------------------------------------ #
    #  Interactive map (Plotly)
    # ------------------------------------------------------------------ #

    def run_interactive_map(self, parks_df):
        """Create an interactive Plotly map with park boundaries."""
        try:
            self.logger.info("Creating interactive US park map...")

            fig = go.Figure()

            # --- Park boundaries (simplified for performance) ---------- #
            try:
                boundaries_gdf = self._fetch_boundaries()
                boundaries_gdf["geometry"] = boundaries_gdf["geometry"].simplify(
                    tolerance=0.005, preserve_topology=True
                )
                visited_codes = set(parks_df.loc[parks_df["visited"], "park_code"])
                self._add_boundaries_to_fig(fig, boundaries_gdf, visited_codes)
            except Exception as e:
                self.logger.error(f"Could not load boundaries: {e}")

            # --- Park points --------------------------------------- #
            visited = parks_df[parks_df["visited"]]
            unvisited = parks_df[~parks_df["visited"]]
            visited_count = int(parks_df["visited"].sum())
            unvisited_count = len(parks_df) - visited_count

            if not unvisited.empty:
                fig.add_trace(
                    go.Scattergeo(
                        lat=unvisited["latitude"],
                        lon=unvisited["longitude"],
                        text=unvisited["park_name"],
                        hovertemplate=(
                            "<b>%{text}</b><br>"
                            "State: %{customdata[0]}<br>"
                            "Status: Not visited"
                            "<extra></extra>"
                        ),
                        customdata=unvisited[["states"]].values,
                        marker=dict(
                            size=8,
                            color=UNVISITED_COLOR,
                            line=dict(width=0.5, color="#888888"),
                        ),
                        name=f"Not visited ({unvisited_count})",
                    )
                )

            if not visited.empty:
                hover_customdata = visited[
                    ["states", "visit_month", "visit_year"]
                ].values
                fig.add_trace(
                    go.Scattergeo(
                        lat=visited["latitude"],
                        lon=visited["longitude"],
                        text=visited["park_name"],
                        hovertemplate=(
                            "<b>%{text}</b><br>"
                            "State: %{customdata[0]}<br>"
                            "Visited: %{customdata[1]} %{customdata[2]}"
                            "<extra></extra>"
                        ),
                        customdata=hover_customdata,
                        marker=dict(
                            size=10,
                            color=VISITED_COLOR,
                            line=dict(width=0.5, color="#1b4332"),
                        ),
                        name=f"Visited ({visited_count})",
                    )
                )

            fig.update_geos(
                scope="usa",
                showland=True,
                landcolor="#f5f5f0",
                showlakes=True,
                lakecolor="#e6f2ff",
                showsubunits=True,
                subunitcolor="#999999",
                subunitwidth=0.4,
                showcountries=True,
                countrycolor="#666666",
            )

            fig.update_layout(
                title=dict(
                    text="US National Park Visits",
                    x=0.5,
                    xanchor="center",
                    font=dict(size=18),
                ),
                showlegend=True,
                legend=dict(
                    yanchor="bottom",
                    y=0.01,
                    xanchor="right",
                    x=0.99,
                    bgcolor="rgba(255,255,255,0.85)",
                    bordercolor="#cccccc",
                    borderwidth=1,
                ),
                width=1200,
                height=800,
                margin=dict(l=0, r=0, t=50, b=0),
            )

            output_path = os.path.join(self.output_dir, "us_park_map_interactive.html")
            fig.write_html(output_path)

            self.logger.success(f"Interactive map saved: {output_path}")
            self.results["interactive_map"] = output_path

        except Exception as e:
            self.logger.error(f"Failed to create interactive map: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise

    def _add_boundaries_to_fig(self, fig, boundaries_gdf, visited_codes):
        """Add park boundary polygons as outlines to the Plotly figure."""
        for _, row in boundaries_gdf.iterrows():
            park_code = row["park_code"]
            geom = row["geometry"]
            if geom.is_empty:
                continue
            is_visited = park_code in visited_codes
            color = VISITED_COLOR if is_visited else UNVISITED_COLOR

            polygons = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]

            for polygon in polygons:
                lons, lats = polygon.exterior.coords.xy
                fig.add_trace(
                    go.Scattergeo(
                        lat=list(lats),
                        lon=list(lons),
                        mode="lines",
                        line=dict(width=1.5, color=color),
                        opacity=0.5,
                        showlegend=False,
                        hoverinfo="skip",
                    )
                )

    # ------------------------------------------------------------------ #
    #  Entry points
    # ------------------------------------------------------------------ #

    def run_all(self):
        """Run both static and interactive map generation."""
        parks_df = self._fetch_parks()
        self.logger.info(
            f"Found {len(parks_df)} parks ({int(parks_df['visited'].sum())} visited)"
        )
        self.run_static_map(parks_df)
        self.run_interactive_map(parks_df)
        return self.results


def run_us_park_map():
    """Convenience function for orchestrator."""
    profiler = USParkMapProfiler()
    return profiler.run_all()


if __name__ == "__main__":
    run_us_park_map()

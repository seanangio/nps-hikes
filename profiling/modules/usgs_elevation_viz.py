#!/usr/bin/env python3
"""
USGS Trail Elevation Profiling Module

This module provides analysis and profiling capabilities for USGS elevation data,
including elevation profile charts and quality metrics.
"""

import json
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from sqlalchemy import text
import os
from typing import Dict, Any, Optional, List

from ..utils import (
    get_db_connection,
    save_results,
    ProfilingLogger,
)
from ..config import PROFILING_MODULES, PROFILING_SETTINGS


class USGSTrailElevationProfiler:
    """USGS trail elevation profiling module."""

    def __init__(self):
        self.config = PROFILING_MODULES.get("usgs_trail_elevation", {})
        self.logger = ProfilingLogger("usgs_trail_elevation")
        self.results = {}
        self.engine = get_db_connection()

    def calculate_grid_size(self, num_trails: int) -> tuple:
        """Calculate optimal grid size for number of trails."""
        if num_trails <= 4:
            return (2, 2)  # 2x2 grid = 4 subplots
        elif num_trails <= 6:
            return (2, 3)  # 2x3 grid = 6 subplots
        elif num_trails <= 9:
            return (3, 3)  # 3x3 grid = 9 subplots
        elif num_trails <= 12:
            return (3, 4)  # 3x4 grid = 12 subplots
        elif num_trails <= 16:
            return (4, 4)  # 4x4 grid = 16 subplots
        elif num_trails <= 20:
            return (4, 5)  # 4x5 grid = 20 subplots
        elif num_trails <= 25:
            return (5, 5)  # 5x5 grid = 25 subplots
        elif num_trails <= 30:
            return (5, 6)  # 5x6 grid = 30 subplots
        else:
            # For very large numbers, use a reasonable maximum
            return (6, 6)  # 6x6 grid = 36 subplots (max)

    def create_elevation_profile_chart(
        self, trail_name: str, elevation_data: List[Dict], ax=None
    ) -> Dict:
        """Create elevation profile chart for a single trail."""
        if not elevation_data:
            return None

        distances = [point["distance_m"] for point in elevation_data]
        elevations = [point["elevation_m"] for point in elevation_data]

        # Plot
        if ax is None:
            fig, ax = plt.subplots(figsize=(8, 4))

        ax.plot(distances, elevations, "b-", linewidth=1.5)
        ax.fill_between(distances, elevations, alpha=0.3, color="lightblue")

        # Formatting
        ax.set_title(trail_name, fontsize=10, fontweight="bold")
        ax.set_xlabel("Distance (km)", fontsize=8)
        ax.set_ylabel("Elevation (m)", fontsize=8)
        ax.grid(True, alpha=0.3)

        # Convert x-axis to km
        ax.set_xticks(ax.get_xticks())
        ax.set_xticklabels([f"{x/1000:.1f}" for x in ax.get_xticks()], fontsize=7)
        ax.tick_params(axis="y", labelsize=7)

        # Calculate stats
        total_gain = sum(
            max(0, elevations[i + 1] - elevations[i])
            for i in range(len(elevations) - 1)
        )
        total_loss = sum(
            max(0, elevations[i] - elevations[i + 1])
            for i in range(len(elevations) - 1)
        )

        return {
            "total_distance_m": distances[-1],
            "elevation_gain_m": total_gain,
            "elevation_loss_m": total_loss,
            "max_elevation_m": max(elevations),
            "min_elevation_m": min(elevations),
        }

    def create_park_elevation_matrix(self, park_code: str) -> str:
        """Create matrix of elevation charts for all trails in a park."""
        self.logger.info(f"Creating elevation matrix for park: {park_code}")

        # Query elevation data for this park
        query = f"""
            SELECT trail_name, elevation_points, collection_status
            FROM usgs_trail_elevations
            WHERE park_code = '{park_code}'
            ORDER BY trail_name
        """

        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                trails_data = result.fetchall()
        except Exception as e:
            self.logger.error(f"Failed to query elevation data: {e}")
            return None

        if not trails_data:
            self.logger.error(f"No elevation data found for park: {park_code}")
            return None

        # Calculate grid size
        num_trails = len(trails_data)
        rows, cols = self.calculate_grid_size(num_trails)

        # Create subplot grid
        fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 3 * rows))
        if rows == 1 and cols == 1:
            axes = [axes]
        elif rows == 1:
            axes = axes
        else:
            axes = axes.flatten()

        # Process each trail
        trail_stats = []
        for i, (trail_name, elevation_points_data, collection_status) in enumerate(
            trails_data
        ):
            try:
                # elevation_points_data is already a Python list from JSONB
                elevation_data = elevation_points_data

                self.logger.info(f"Processing trail {i+1}/{num_trails}: {trail_name}")

                # Create chart
                stats = self.create_elevation_profile_chart(
                    trail_name, elevation_data, axes[i]
                )
                if stats:
                    stats["trail_name"] = trail_name
                    stats["collection_status"] = collection_status
                    trail_stats.append(stats)

            except Exception as e:
                self.logger.error(f"Failed to process trail {trail_name}: {e}")
                # Empty subplot with error message
                axes[i].text(
                    0.5,
                    0.5,
                    f"Error: {trail_name}",
                    ha="center",
                    va="center",
                    transform=axes[i].transAxes,
                    fontsize=8,
                )
                axes[i].set_title(trail_name, fontsize=10)

        # Hide unused subplots
        for i in range(num_trails, len(axes)):
            axes[i].set_visible(False)

        # Overall title
        fig.suptitle(
            f"Elevation Profiles - {park_code.upper()}", fontsize=16, fontweight="bold"
        )
        plt.tight_layout()

        # Save
        output_dir = "profiling_results/elevation_changes"
        os.makedirs(output_dir, exist_ok=True)
        output_path = f"{output_dir}/{park_code}_elevation_matrix.png"
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()

        self.logger.info(f"Created elevation matrix: {output_path}")

        # Save trail statistics
        if trail_stats:
            stats_df = pd.DataFrame(trail_stats)
            stats_path = f"profiling_results/{park_code}_usgs_elevation_stats.csv"
            stats_df.to_csv(stats_path, index=False)
            self.logger.info(f"Saved elevation statistics: {stats_path}")

        return output_path

    def run_elevation_summary(self, park_code: str):
        """Run elevation data summary analysis."""
        try:
            self.logger.info(f"Running elevation summary for park: {park_code}")

            # Query elevation data summary
            query = f"""
                SELECT 
                    COUNT(*) as total_trails,
                    COUNT(CASE WHEN collection_status = 'COMPLETE' THEN 1 END) as complete_trails,
                    COUNT(CASE WHEN collection_status = 'PARTIAL' THEN 1 END) as partial_trails,
                    COUNT(CASE WHEN collection_status = 'FAILED' THEN 1 END) as failed_trails,
                    AVG(total_points_count) as avg_points_per_trail
                FROM usgs_trail_elevations
                WHERE park_code = '{park_code}'
            """

            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                summary_data = result.fetchone()

            if summary_data and summary_data[0] > 0:  # total_trails > 0
                summary_df = pd.DataFrame(
                    [
                        {
                            "park_code": park_code,
                            "total_trails": summary_data[0],
                            "complete_trails": summary_data[1],
                            "partial_trails": summary_data[2],
                            "failed_trails": summary_data[3],
                            "avg_points_per_trail": (
                                round(summary_data[4], 1) if summary_data[4] else 0
                            ),
                        }
                    ]
                )

                # Save results
                save_results(summary_df, f"usgs_elevation_summary_{park_code}.csv")

                self.results[f"elevation_summary_{park_code}"] = len(summary_df)
                self.logger.success(
                    f"Elevation summary analysis completed for {park_code}"
                )

                return summary_df
            else:
                self.logger.error(f"No elevation data found for park: {park_code}")
                return None

        except Exception as e:
            self.logger.error(f"Failed to run elevation summary for {park_code}: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise
            return None

    def run_park_elevation_profiling(self, park_code: str):
        """Run complete elevation profiling for a park."""
        self.logger.info(f"Running elevation profiling for park: {park_code}")

        try:
            # Create elevation matrix
            matrix_path = self.create_park_elevation_matrix(park_code)

            # Run summary analysis
            summary_df = self.run_elevation_summary(park_code)

            if matrix_path:
                self.logger.success(f"Elevation profiling completed for {park_code}")
                return {"matrix_path": matrix_path, "summary_data": summary_df}
            else:
                self.logger.error(f"No elevation data found for {park_code}")
                return None

        except Exception as e:
            self.logger.error(f"Elevation profiling failed for {park_code}: {e}")
            if not PROFILING_SETTINGS["continue_on_error"]:
                raise
            return None

    def get_parks_with_elevation_data(self):
        """Get list of all parks that have elevation data."""
        query = """
            SELECT DISTINCT park_code 
            FROM usgs_trail_elevations 
            WHERE collection_status IN ('COMPLETE', 'PARTIAL')
            ORDER BY park_code
        """

        with self.engine.connect() as conn:
            result = conn.execute(text(query))
            parks = [row[0] for row in result.fetchall()]

        return parks

    def run_all_parks_elevation_profiling(self):
        """Generate elevation matrices for all parks with elevation data."""
        self.logger.info("🔍 Finding parks with elevation data...")

        parks = self.get_parks_with_elevation_data()
        self.logger.info(
            f"📊 Found {len(parks)} parks with elevation data: {', '.join(parks)}"
        )

        if not parks:
            self.logger.error("❌ No parks with elevation data found!")
            return {"successful": 0, "failed": 0, "total": 0}

        self.logger.info(f"🎨 Generating elevation matrices for {len(parks)} parks...")

        successful = 0
        failed = 0

        for i, park_code in enumerate(parks, 1):
            self.logger.info(f"📋 Processing park {i}/{len(parks)}: {park_code}")

            try:
                result = self.run_park_elevation_profiling(park_code)

                if result and result.get("matrix_path"):
                    self.logger.success(
                        f"✅ Successfully generated elevation matrix for {park_code}"
                    )
                    self.logger.info(f"   📁 Saved to: {result['matrix_path']}")
                    successful += 1
                else:
                    self.logger.warning(f"⚠️  No elevation data found for {park_code}")
                    failed += 1

            except Exception as e:
                self.logger.error(f"❌ Failed to process {park_code}: {str(e)}")
                failed += 1

        self.logger.success(f"🎉 Processing complete!")
        self.logger.info(f"✅ Successful: {successful}")
        self.logger.info(f"❌ Failed: {failed}")
        self.logger.info(
            f"📁 Elevation matrices saved to: profiling_results/elevation_changes/"
        )

        return {"successful": successful, "failed": failed, "total": len(parks)}

    def run_all(self, park_code: str = None):
        """Run all elevation profiling analyses."""
        if park_code:
            return self.run_park_elevation_profiling(park_code)
        else:
            # If no park code provided, run for all parks
            return self.run_all_parks_elevation_profiling()


# Convenience function
def run_usgs_elevation_viz():
    """Convenience function to run USGS elevation visualization profiling."""
    profiler = USGSTrailElevationProfiler()
    return profiler.run_all()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Profile USGS elevation visualization data"
    )
    parser.add_argument(
        "park_code",
        nargs="?",
        help="Park code to profile (optional, defaults to all parks)",
    )

    args = parser.parse_args()

    profiler = USGSTrailElevationProfiler()

    if args.park_code:
        result = profiler.run_park_elevation_profiling(args.park_code)
        if result:
            print(f"Elevation matrix created: {result['matrix_path']}")
            if result["summary_data"] is not None:
                print(f"Summary data:")
                print(result["summary_data"].to_string(index=False))
        else:
            print("No elevation data found for this park")
    else:
        result = profiler.run_all_parks_elevation_profiling()
        print(
            f"Batch processing complete: {result['successful']} successful, {result['failed']} failed"
        )

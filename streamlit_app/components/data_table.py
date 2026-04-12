"""
Data table component for displaying trail information.

Provides a sortable, interactive table of trails with links to 3D visualizations.
"""

from typing import Any

import pandas as pd
import streamlit as st

from streamlit_app.utils.export import trails_to_csv, trails_to_geojson
from streamlit_app.utils.formatting import format_miles, format_trail_name


def render_trail_table(
    trails: list[dict[str, Any]],
    api_base_url: str,
    all_parks: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """
    Render an interactive table of trails.

    Args:
        trails: List of trail dicts from API
        api_base_url: Base URL of the API (for 3D viz links)
        all_parks: Optional full park list, used to compute the
            reactive Parks/States counts above the table.

    Returns:
        Full trail dict of clicked trail (if any), or None
    """
    if not trails:
        st.info("No trails to display. Select a park and apply filters.")
        return None

    # Compute reactive aggregates from the currently filtered trail list.
    total_miles = sum(t.get("length_miles", 0) for t in trails)
    hiked_count = sum(1 for t in trails if t.get("hiked"))
    viz_3d_count = sum(1 for t in trails if t.get("viz_3d_available"))

    unique_park_codes = {t.get("park_code") for t in trails if t.get("park_code")}
    parks_count = len(unique_park_codes)

    states_set: set[str] = set()
    if all_parks:
        park_lookup = {p["park_code"]: p for p in all_parks}
        for code in unique_park_codes:
            park = park_lookup.get(code)
            if park and park.get("states"):
                for state in park["states"].split(","):
                    state = state.strip()
                    if state:
                        states_set.add(state)
    states_count = len(states_set)

    # Header with export buttons
    col_header, col_csv, col_geojson = st.columns([3, 1, 1])
    with col_header:
        st.subheader(f"Trails ({len(trails)} total)")

    with col_csv:
        csv_data = trails_to_csv(trails)
        st.download_button(
            label="📥 CSV",
            data=csv_data,
            file_name="nps_trails.csv",
            mime="text/csv",
            key="download_csv_btn",
            help="Download trails as CSV",
            use_container_width=True,
        )

    with col_geojson:
        geojson_data = trails_to_geojson(trails)
        st.download_button(
            label="📥 GeoJSON",
            data=geojson_data,
            file_name="nps_trails.geojson",
            mime="application/geo+json",
            key="download_geojson_btn",
            help="Download trails as GeoJSON",
            use_container_width=True,
        )

    # Convert trails to DataFrame-friendly format
    rows = []
    for trail in trails:
        trail_name = format_trail_name(trail)
        park_name = trail.get("park_name", "")
        length = trail.get("length_miles", 0)
        source = trail.get("source", "")
        hiked = trail.get("hiked", False)
        viz_3d_available = trail.get("viz_3d_available", False)
        viz_3d_slug = trail.get("viz_3d_slug")
        park_code = trail.get("park_code")

        # Format 3D viz URL
        viz_url = None
        if viz_3d_available and viz_3d_slug and park_code:
            viz_url = f"{api_base_url}/parks/{park_code}/trails/{viz_3d_slug}/viz/3d"

        rows.append(
            {
                "Trail": trail_name,
                "Park": park_name,
                "Length": length,
                "Source": source,
                "Hiked": "✓" if hiked else "✗",
                "3D Viz": viz_url if viz_url else None,
            }
        )

    # Create DataFrame
    df = pd.DataFrame(rows)

    # Display table using st.dataframe with column configuration and row selection
    event = st.dataframe(
        df,
        column_config={
            "Trail": st.column_config.TextColumn("Trail", width="medium"),
            "Park": st.column_config.TextColumn("Park", width="small"),
            "Length": st.column_config.NumberColumn(
                "Length (mi)",
                width="small",
                format="%.1f",
            ),
            "Source": st.column_config.TextColumn("Source", width="small"),
            "Hiked": st.column_config.TextColumn("Hiked", width="small"),
            "3D Viz": st.column_config.LinkColumn(
                "3D Viz",
                width="small",
                display_text="View",
            ),
        },
        hide_index=True,
        use_container_width=True,
        height=400,
        on_select="rerun",
        selection_mode="single-row",
        key="trail_table",
    )

    # Reactive summary statistics below table — these update with filters.
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Miles", format_miles(total_miles))
    col2.metric("Parks", parks_count)
    col3.metric("States", states_count)
    col4.metric("Hiked", f"{hiked_count} / {len(trails)}")
    col5.metric("With 3D Viz", viz_3d_count)

    # Return selected trail if a row was clicked
    selected_rows = event.selection.rows
    if selected_rows:
        row_idx = selected_rows[0]
        if 0 <= row_idx < len(trails):
            return trails[row_idx]

    return None


def render_empty_table_placeholder() -> None:
    """Render a placeholder when no parks are selected."""
    st.subheader("Trails")
    st.info(
        "👈 Select one or more parks from the sidebar to view trails on the map and in this table."
    )

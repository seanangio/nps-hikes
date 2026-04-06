"""
NPS Hikes Streamlit Web Application

An interactive map-based web app for exploring National Park hiking trails.
Provides dual-mode interaction: GUI filters and natural language queries.

Phase 1 MVP Features:
- Interactive map with park markers
- Park selection and state filtering
- Trail visualization with boundaries
- Data table with sortable columns
- Trail filtering (hiked, length, source, type, 3D viz)

Usage:
    streamlit run streamlit_app/app.py

Environment Variables:
    NPS_API_URL: API base URL (default: http://localhost:8001)
"""

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import streamlit as st

# Add parent directory to path to allow imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from streamlit_app.api.client import (
    API_BASE_URL,
    APIError,
    fetch_hiked_points,
    fetch_park_summary,
    fetch_parks,
    fetch_trails,
    test_api_connection,
)
from streamlit_app.components.data_table import (
    render_empty_table_placeholder,
    render_trail_table,
)
from streamlit_app.components.map import render_map
from streamlit_app.components.sidebar import render_sidebar
from streamlit_app.utils.formatting import compute_bounds
from streamlit_app.utils.state import (
    cache_park_data,
    get_cached_park_data,
    initialize_session_state,
)

# Page configuration
st.set_page_config(
    page_title="NPS Hikes Explorer",
    page_icon="🏞️",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main() -> None:
    """Main application entry point."""

    # Initialize session state
    initialize_session_state()

    # Check API connection
    if not test_api_connection():
        st.error(
            f"⚠️ Cannot connect to the NPS Hikes API at `{API_BASE_URL}`. "
            f"Please ensure the API server is running.\n\n"
            f"To start the API:\n"
            f"```bash\n"
            f"docker compose up -d\n"
            f"# OR\n"
            f"uvicorn api.main:app --reload --port 8001\n"
            f"```"
        )
        st.stop()

    # Fetch all parks (cached)
    try:
        all_parks_response = fetch_parks()
        all_parks = all_parks_response["parks"]
        st.session_state.all_parks_data = all_parks_response
    except APIError as e:
        st.error(f"Failed to fetch parks: {e}")
        st.stop()

    # === HEADER ===
    st.title("NPS Hikes Interactive Explorer")

    # === FETCH PARK SUMMARIES FOR THE CURRENT SELECTION ===
    # Read the multiselect widget's session state directly so we pick up
    # the selection the user just made on this rerun. Falling back to
    # `selected_parks` covers the very first script run, before the
    # widget has been instantiated.
    current_selection = st.session_state.get(
        "park_multiselect", st.session_state.selected_parks
    )
    park_summaries: dict[str, dict] = {}
    summary_errors: dict[str, str] = {}
    if current_selection:
        with (
            st.spinner("Loading park summaries..."),
            ThreadPoolExecutor(max_workers=4) as executor,
        ):
            future_to_code = {
                executor.submit(fetch_park_summary, park_code): park_code
                for park_code in current_selection
            }
            for future in as_completed(future_to_code):
                park_code = future_to_code[future]
                try:
                    park_summaries[park_code] = future.result()
                except APIError as e:
                    summary_errors[park_code] = str(e)
                    print(f"[streamlit] Failed to fetch summary for {park_code}: {e}")

    # === SIDEBAR (render once with all data) ===
    sidebar_data = render_sidebar(
        all_parks=all_parks,
        selected_parks=current_selection,
        park_summaries=park_summaries,
        summary_errors=summary_errors,
    )

    # Note: "Clear All" button uses an on_click callback in sidebar.py
    # to clear widget state before the multiselect is re-instantiated.

    # Update session state with sidebar selections
    selected_parks = sidebar_data["selected_parks"]
    st.session_state.selected_parks = selected_parks

    # === FETCH DATA FOR SELECTED PARKS ===
    park_data = {}  # park_code -> {boundary, trails, hiked_points}

    for park_code in selected_parks:
        # Check if already cached
        cached_boundary, cached_trails, cached_hiked_points = get_cached_park_data(
            park_code
        )

        # Fetch boundary if not cached
        if cached_boundary is None:
            try:
                boundary_response = fetch_parks(park_code=park_code, boundary=True)
                parks = boundary_response.get("parks", [])
                if parks and parks[0].get("boundary"):
                    cached_boundary = parks[0]["boundary"]
                    cache_park_data(park_code, boundary=cached_boundary)
            except APIError:
                pass  # Skip if unavailable

        # Fetch trails with filters and geometry
        try:
            trails_response = fetch_trails(
                park_code=park_code,
                hiked=sidebar_data["filter_hiked"],
                min_length=sidebar_data["filter_min_length"]
                if sidebar_data["filter_min_length"] > 0
                else None,
                max_length=sidebar_data["filter_max_length"]
                if sidebar_data["filter_max_length"] < 20
                else None,
                source=sidebar_data["filter_source"],
                viz_3d=sidebar_data["filter_viz_3d"],
                geojson=True,  # Include geometry for map rendering
                limit=1000,
            )
            cached_trails = trails_response
            # Note: We don't cache filtered trails, only fetch fresh each time
        except APIError as e:
            st.error(f"Failed to fetch trails for {park_code}: {e}")
            cached_trails = {"trails": [], "trail_count": 0, "total_miles": 0}

        # Fetch hiked points if not cached
        if cached_hiked_points is None:
            try:
                hiked_points_response = fetch_hiked_points(park_code=park_code)
                cached_hiked_points = hiked_points_response
                cache_park_data(park_code, hiked_points=cached_hiked_points)
            except APIError:
                pass  # Skip if unavailable

        # Store in park_data dict
        park_data[park_code] = {
            "boundary": cached_boundary,
            "trails": cached_trails,
            "hiked_points": cached_hiked_points,
        }

    # === APPLY CLIENT-SIDE TRAIL NAME FILTER ===
    # Filter trails in park_data by name search (for map rendering)
    if sidebar_data.get("filter_trail_name"):
        search_term = sidebar_data["filter_trail_name"].lower()
        for park_code in park_data:
            if park_data[park_code].get("trails"):
                trails_data = park_data[park_code]["trails"]
                filtered_trails = [
                    trail
                    for trail in trails_data.get("trails", [])
                    if search_term in trail.get("trail_name", "").lower()
                ]
                # Update the trails data with filtered list
                park_data[park_code]["trails"] = {
                    **trails_data,
                    "trails": filtered_trails,
                    "trail_count": len(filtered_trails),
                }

    # === COMPUTE MAP CENTER AND ZOOM ===
    if selected_parks:
        selected_park_objs = [p for p in all_parks if p["park_code"] in selected_parks]
        center, zoom = compute_bounds(selected_park_objs)
    else:
        # Default to US center
        center, zoom = [39.8283, -98.5795], 4

    # === RENDER MAP ===
    render_map(
        all_parks=all_parks,
        selected_parks=selected_parks,
        park_data=park_data,
        center=center,
        zoom=zoom,
        highlighted_trail_id=None,  # Phase 1: no highlighting yet
    )

    st.divider()

    # === RENDER TRAIL TABLE ===
    # Combine trails from all selected parks
    all_trails = []
    for park_code in selected_parks:
        trails_data = park_data.get(park_code, {}).get("trails", {})
        trails = trails_data.get("trails", [])
        all_trails.extend(trails)

    # Apply client-side trail name search filter
    if sidebar_data.get("filter_trail_name"):
        search_term = sidebar_data["filter_trail_name"].lower()
        all_trails = [
            trail
            for trail in all_trails
            if search_term in trail.get("trail_name", "").lower()
        ]

    if all_trails:
        render_trail_table(all_trails, api_base_url=API_BASE_URL, all_parks=all_parks)
    else:
        render_empty_table_placeholder()


if __name__ == "__main__":
    main()

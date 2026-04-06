"""
Session state management for the Streamlit app.

Provides functions to initialize and manage Streamlit session state,
including selected parks, filters, and cached data.
"""

import streamlit as st


def initialize_session_state() -> None:
    """
    Initialize session state variables if they don't exist.

    This should be called at the start of the app to ensure all
    required session state keys are present with default values.
    """
    # Selected parks (list of park codes)
    if "selected_parks" not in st.session_state:
        st.session_state.selected_parks = []

    # Filter states
    if "filter_state" not in st.session_state:
        st.session_state.filter_state = None

    if "filter_visited" not in st.session_state:
        st.session_state.filter_visited = None

    if "filter_hiked" not in st.session_state:
        st.session_state.filter_hiked = None

    if "filter_min_length" not in st.session_state:
        st.session_state.filter_min_length = 0.0

    if "filter_max_length" not in st.session_state:
        st.session_state.filter_max_length = 100.0

    if "filter_source" not in st.session_state:
        st.session_state.filter_source = None

    if "filter_trail_type" not in st.session_state:
        st.session_state.filter_trail_type = None

    if "filter_viz_3d" not in st.session_state:
        st.session_state.filter_viz_3d = None

    # Cached data (to avoid redundant API calls)
    if "all_parks_data" not in st.session_state:
        st.session_state.all_parks_data = None

    if "park_boundaries" not in st.session_state:
        st.session_state.park_boundaries = {}  # park_code -> boundary GeoJSON

    if "park_trails" not in st.session_state:
        st.session_state.park_trails = {}  # park_code -> trails data

    if "park_hiked_points" not in st.session_state:
        st.session_state.park_hiked_points = {}  # park_code -> hiked points

    # UI state
    if "highlighted_trail" not in st.session_state:
        st.session_state.highlighted_trail = None

    if "map_center" not in st.session_state:
        st.session_state.map_center = [39.8283, -98.5795]  # Center of US

    if "map_zoom" not in st.session_state:
        st.session_state.map_zoom = 4  # US-level zoom


def add_selected_park(park_code: str) -> None:
    """
    Add a park to the selected parks list.

    Args:
        park_code: 4-character park code to add
    """
    if park_code not in st.session_state.selected_parks:
        st.session_state.selected_parks.append(park_code)


def remove_selected_park(park_code: str) -> None:
    """
    Remove a park from the selected parks list.

    Args:
        park_code: 4-character park code to remove
    """
    if park_code in st.session_state.selected_parks:
        st.session_state.selected_parks.remove(park_code)


def clear_selected_parks() -> None:
    """Clear all selected parks."""
    st.session_state.selected_parks = []


def set_highlighted_trail(trail_id: str | None) -> None:
    """
    Set the highlighted trail (for table row clicks).

    Args:
        trail_id: Trail ID to highlight, or None to clear
    """
    st.session_state.highlighted_trail = trail_id


def update_map_view(center: list[float], zoom: int) -> None:
    """
    Update the map center and zoom level.

    Args:
        center: [lat, lon] coordinates for map center
        zoom: Zoom level
    """
    st.session_state.map_center = center
    st.session_state.map_zoom = zoom


def cache_park_data(
    park_code: str,
    boundary: dict | None = None,
    trails: dict | None = None,
    hiked_points: dict | None = None,
) -> None:
    """
    Cache park-specific data in session state.

    Args:
        park_code: 4-character park code
        boundary: Park boundary GeoJSON (if fetched)
        trails: Trails data (if fetched)
        hiked_points: Hiked points data (if fetched)
    """
    if boundary is not None:
        st.session_state.park_boundaries[park_code] = boundary

    if trails is not None:
        st.session_state.park_trails[park_code] = trails

    if hiked_points is not None:
        st.session_state.park_hiked_points[park_code] = hiked_points


def get_cached_park_data(
    park_code: str,
) -> tuple[dict | None, dict | None, dict | None]:
    """
    Retrieve cached park data from session state.

    Args:
        park_code: 4-character park code

    Returns:
        Tuple of (boundary, trails, hiked_points), any of which may be None
    """
    boundary = st.session_state.park_boundaries.get(park_code)
    trails = st.session_state.park_trails.get(park_code)
    hiked_points = st.session_state.park_hiked_points.get(park_code)

    return boundary, trails, hiked_points

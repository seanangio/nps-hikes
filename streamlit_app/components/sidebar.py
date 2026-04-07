"""
Sidebar component with filters and park selection controls.

Provides UI controls for filtering parks and trails, managing park selection,
and displaying park summary statistics.
"""

from typing import Any

import streamlit as st

from streamlit_app.components.nlq import render_nlq_form
from streamlit_app.utils.formatting import format_miles, format_park_name


def _clear_park_selection() -> None:
    """Callback to clear the park multiselect widget state.

    Must run as a button on_click callback (before widget instantiation)
    to avoid StreamlitAPIException about modifying widget state after creation.
    """
    if "park_multiselect" in st.session_state:
        st.session_state["park_multiselect"] = []
    st.session_state["selected_parks"] = []


def _reset_trail_filters() -> None:
    """Callback to reset all trail filter widgets to their defaults.

    Like _clear_park_selection, this must run as a button on_click callback
    so the widget state is reset BEFORE the widgets are re-instantiated on
    the next script run, avoiding StreamlitAPIException.
    """
    st.session_state["filter_trail_name_input"] = ""
    st.session_state["filter_hiked_radio"] = "All Trails"
    st.session_state["filter_length_slider"] = (0.0, 20.0)
    st.session_state["filter_source_select"] = "All Sources"
    st.session_state["filter_viz_3d_radio"] = "All Trails"


def render_sidebar(
    all_parks: list[dict[str, Any]],
    selected_parks: list[str],
    park_summaries: dict[str, dict[str, Any]],
    summary_errors: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Render the sidebar with filters and controls.

    Args:
        all_parks: List of all park dicts from API
        selected_parks: List of currently selected park codes
        park_summaries: Dict mapping park_code to summary data
        summary_errors: Dict mapping park_code to error message for any
            park whose summary failed to load. Surfaced as warnings in the
            summary section.

    Returns:
        Dict containing all filter values and selection changes
    """
    st.sidebar.title("🏞️ NPS Hikes Explorer")

    # === NATURAL LANGUAGE QUERY ===
    # Rendered first so it sits at the very top of the sidebar.
    # Submission sets ``nlq_pending`` which is processed at the top
    # of main() on the subsequent rerun.
    render_nlq_form()

    st.sidebar.divider()

    # === PARK SELECTION SECTION ===
    st.sidebar.header("📍 Select Parks")

    # State filter (affects available parks)
    # Parse multi-state values like "CA,NV" into individual states
    all_states_raw = [
        park.get("states", "") for park in all_parks if park.get("states")
    ]
    all_states = set()
    for states_str in all_states_raw:
        # Split by comma and strip whitespace
        states = [s.strip() for s in states_str.split(",")]
        all_states.update(states)
    all_states = sorted(all_states)

    filter_state = st.sidebar.selectbox(
        "Filter by State",
        options=["All States", *all_states],
        index=0,
        key="filter_state_select",
        help="Narrow park selection by state",
    )
    filter_state = None if filter_state == "All States" else filter_state

    # Visited filter
    filter_visited_options = ["All Parks", "Visited Only", "Not Yet Visited"]
    filter_visited_idx = st.sidebar.radio(
        "Visit Status",
        options=filter_visited_options,
        index=0,
        key="filter_visited_radio",
        help="Filter parks by visit status",
    )
    if filter_visited_idx == "Visited Only":
        filter_visited = True
    elif filter_visited_idx == "Not Yet Visited":
        filter_visited = False
    else:
        filter_visited = None

    # Filter parks list based on state and visited status
    filtered_parks = all_parks
    if filter_state:
        # Check if park's states string contains the selected state
        filtered_parks = [
            p
            for p in filtered_parks
            if filter_state in [s.strip() for s in p.get("states", "").split(",")]
        ]
    if filter_visited is not None:
        filtered_parks = [
            p
            for p in filtered_parks
            if bool(p.get("visit_month") and p.get("visit_year")) == filter_visited
        ]

    # Sort parks by name
    filtered_parks = sorted(
        filtered_parks, key=lambda p: p.get("park_name", p.get("full_name", ""))
    )

    # Park multi-select
    park_options = {p["park_code"]: format_park_name(p) for p in filtered_parks}

    if park_options:
        # Drop any stale session_state values that aren't in the current
        # filtered options (e.g. the user narrowed by state and the
        # previously-selected park is no longer visible). This must
        # happen BEFORE the widget instantiates so we can safely mutate
        # session state.
        current_selection = st.session_state.get("park_multiselect", [])
        valid_selection = [c for c in current_selection if c in park_options]
        if valid_selection != current_selection:
            st.session_state["park_multiselect"] = valid_selection

        # Note: no ``default=`` argument — the widget is driven entirely
        # by ``st.session_state["park_multiselect"]``. Mixing ``default=``
        # with session-state writes (which the NLQ flow does) triggers
        # a Streamlit warning.
        selected_park_codes = st.sidebar.multiselect(
            "Select Park(s)",
            options=list(park_options.keys()),
            format_func=lambda code: park_options.get(code, code),
            key="park_multiselect",
            help="Select one or more parks to view trails",
        )
    else:
        st.sidebar.warning("No parks match the current filters")
        selected_park_codes = []

    # Quick actions
    col1, _col2 = st.sidebar.columns(2)
    clear_selection = col1.button(
        "Clear All",
        key="clear_parks_btn",
        use_container_width=True,
        on_click=_clear_park_selection,
    )

    st.sidebar.divider()

    # === TRAIL FILTERS SECTION ===
    st.sidebar.header("🥾 Filter Trails")

    # Reset filters button (mirrors the "Clear All" button in the parks section).
    # MUST use on_click callback so widget state is updated before widgets
    # are re-instantiated on the next script run.
    reset_col1, _reset_col2 = st.sidebar.columns(2)
    reset_col1.button(
        "Reset Filters",
        key="reset_filters_btn",
        use_container_width=True,
        on_click=_reset_trail_filters,
        help="Reset all trail filters to their defaults",
    )

    # Trail name search
    filter_trail_name = st.sidebar.text_input(
        "Search Trail Name",
        value="",
        key="filter_trail_name_input",
        placeholder="Enter trail name...",
        help="Filter trails by name (case-insensitive)",
    )

    # Hiked status
    filter_hiked_options = ["All Trails", "Hiked Only", "Not Yet Hiked"]
    filter_hiked_idx = st.sidebar.radio(
        "Hiking Status",
        options=filter_hiked_options,
        index=0,
        key="filter_hiked_radio",
        help="Filter trails by whether you've hiked them",
    )
    if filter_hiked_idx == "Hiked Only":
        filter_hiked = True
    elif filter_hiked_idx == "Not Yet Hiked":
        filter_hiked = False
    else:
        filter_hiked = None

    # Trail length slider
    # Seed session state before instantiating the widget so we can
    # drop the ``value=`` argument (which conflicts with the NLQ flow
    # writing to the same session state key). Passing a tuple here
    # ensures Streamlit infers range-slider mode on first render.
    if "filter_length_slider" not in st.session_state:
        st.session_state["filter_length_slider"] = (0.0, 20.0)
    filter_min_length, filter_max_length = st.sidebar.slider(
        "Trail Length (miles)",
        min_value=0.0,
        max_value=20.0,
        step=0.5,
        key="filter_length_slider",
        help="Filter by trail length range",
    )

    # Source filter
    filter_source = st.sidebar.selectbox(
        "Data Source",
        options=["All Sources", "TNM", "OSM"],
        index=0,
        key="filter_source_select",
        help="Filter by data source (The National Map or OpenStreetMap)",
    )
    filter_source = None if filter_source == "All Sources" else filter_source

    # 3D viz filter
    filter_viz_3d_options = ["All Trails", "With 3D Viz", "Without 3D Viz"]
    filter_viz_3d_idx = st.sidebar.radio(
        "3D Visualization",
        options=filter_viz_3d_options,
        index=0,
        key="filter_viz_3d_radio",
        help="Filter trails by 3D visualization availability",
    )
    if filter_viz_3d_idx == "With 3D Viz":
        filter_viz_3d = True
    elif filter_viz_3d_idx == "Without 3D Viz":
        filter_viz_3d = False
    else:
        filter_viz_3d = None

    st.sidebar.divider()

    # === PARK SUMMARIES SECTION ===
    summary_errors = summary_errors or {}
    if selected_park_codes and (park_summaries or summary_errors):
        st.sidebar.header("📊 Selected Parks Summary")

        # Surface any failed summary fetches so the user knows the section
        # isn't silently broken.
        for failed_code, err_msg in summary_errors.items():
            st.sidebar.warning(f"Could not load summary for `{failed_code}`: {err_msg}")

        for park_code in selected_park_codes:
            summary = park_summaries.get(park_code)
            if not summary:
                continue

            park_name = summary.get("park_name", park_code)

            with st.sidebar.expander(f"📍 {park_name}", expanded=False):
                st.write(f"**Total Trails:** {summary.get('total_trails', 0)}")
                st.write(
                    f"**Total Miles:** {format_miles(summary.get('total_miles', 0))}"
                )
                st.write(f"**Hiked Trails:** {summary.get('hiked_trails', 0)}")
                st.write(
                    f"**Hiked Miles:** {format_miles(summary.get('hiked_miles', 0))}"
                )
                st.write(f"**3D Viz Trails:** {summary.get('viz_3d_count', 0)}")

                source_breakdown = summary.get("source_breakdown", {})
                st.write(
                    f"**Sources:** {source_breakdown.get('tnm', 0)} TNM, {source_breakdown.get('osm', 0)} OSM"
                )

    # Return all filter values and actions
    return {
        "selected_parks": selected_park_codes,
        "clear_selection": clear_selection,
        "filter_state": filter_state,
        "filter_visited": filter_visited,
        "filter_trail_name": filter_trail_name.strip() if filter_trail_name else None,
        "filter_hiked": filter_hiked,
        "filter_min_length": filter_min_length,
        "filter_max_length": filter_max_length,
        "filter_source": filter_source,
        "filter_viz_3d": filter_viz_3d,
    }

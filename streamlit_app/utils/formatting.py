"""
Data formatting and display utilities for the Streamlit app.

Provides functions to format numbers, compute bounding boxes,
and transform API data for display.
"""

from typing import Any


def format_miles(miles: float) -> str:
    """
    Format mileage for display.

    Args:
        miles: Distance in miles

    Returns:
        Formatted string like "5.2 mi" or "0.3 mi"
    """
    return f"{miles:.1f} mi"


def format_park_name(park: dict[str, Any]) -> str:
    """
    Format park name for display in dropdowns.

    Args:
        park: Park dict from API

    Returns:
        Formatted string like "Yosemite (CA)" or "Yellowstone (WY, MT, ID)"
    """
    name = park.get("park_name", park.get("full_name", "Unknown"))
    states = park.get("states", "")

    if states:
        return f"{name} ({states})"
    return name


def format_trail_name(trail: dict[str, Any]) -> str:
    """
    Format trail name for display, handling unnamed trails.

    Args:
        trail: Trail dict from API

    Returns:
        Trail name or "(Unnamed Trail)" if null
    """
    name = trail.get("trail_name")
    return name if name else "(Unnamed Trail)"


def compute_bounds(parks: list[dict[str, Any]]) -> tuple[list[float], int]:
    """
    Compute map bounds (center and zoom) for a list of parks.

    Args:
        parks: List of park dicts with latitude/longitude

    Returns:
        Tuple of ([lat, lon], zoom_level)
    """
    if not parks:
        # Default to US center
        return [39.8283, -98.5795], 4

    # Extract coordinates
    coords = [
        (p["latitude"], p["longitude"])
        for p in parks
        if p.get("latitude") and p.get("longitude")
    ]

    if not coords:
        return [39.8283, -98.5795], 4

    # Compute bounding box
    lats = [c[0] for c in coords]
    lons = [c[1] for c in coords]

    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)

    # Compute center
    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2

    # Estimate zoom level based on span
    lat_span = max_lat - min_lat
    lon_span = max_lon - min_lon
    max_span = max(lat_span, lon_span)

    # Rough zoom estimation
    if max_span > 50:
        zoom = 4
    elif max_span > 20:
        zoom = 5
    elif max_span > 10:
        zoom = 6
    elif max_span > 5:
        zoom = 7
    elif max_span > 2:
        zoom = 8
    else:
        zoom = 9

    return [center_lat, center_lon], zoom


def get_visit_status_color(park: dict[str, Any]) -> str:
    """
    Get marker color based on park visit status.

    Args:
        park: Park dict from API

    Returns:
        Folium color string ('green' for visited, 'gray' for unvisited)
    """
    visit_month = park.get("visit_month")
    visit_year = park.get("visit_year")

    if visit_month and visit_year:
        return "green"
    return "gray"


def get_trail_color(trail: dict[str, Any]) -> str:
    """
    Get trail line color based on hiking status.

    Args:
        trail: Trail dict from API

    Returns:
        CSS color string ('green' for hiked, 'gray' for not hiked)
    """
    return "green" if trail.get("hiked") else "gray"


def get_trail_weight(trail: dict[str, Any], highlighted_trail_id: str | None) -> int:
    """
    Get trail line weight based on highlight status.

    Args:
        trail: Trail dict from API
        highlighted_trail_id: ID of currently highlighted trail (or None)

    Returns:
        Line weight in pixels
    """
    trail_id = trail.get("trail_id")

    if highlighted_trail_id and trail_id == highlighted_trail_id:
        return 5  # Highlighted trail
    return 3 if trail.get("hiked") else 2  # Normal trails


def trails_to_dataframe_rows(trails: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Convert trails list to rows suitable for st.dataframe.

    Args:
        trails: List of trail dicts from API

    Returns:
        List of dicts with formatted display values
    """
    rows = []
    for trail in trails:
        rows.append(
            {
                "Trail": format_trail_name(trail),
                "Park": trail.get("park_name", ""),
                "Length": format_miles(trail.get("length_miles", 0)),
                "Source": trail.get("source", ""),
                "Hiked": "✓" if trail.get("hiked") else "✗",
                "3D Viz": "✓" if trail.get("viz_3d_available") else "—",
                "_trail_id": trail.get("trail_id"),  # Hidden column for interaction
            }
        )
    return rows

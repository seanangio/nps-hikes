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


def format_park_visit_line(park: dict[str, Any]) -> str:
    """
    Format states and visit info into a single line.

    Args:
        park: Park dict from API

    Returns:
        Formatted string like "CA (June 2023)" or "CA, NV (Not visited)"
    """
    states = park.get("states", "")
    visit_month = park.get("visit_month")
    visit_year = park.get("visit_year")

    if visit_month and visit_year:
        visit_info = f"{visit_month} {visit_year}"
    else:
        visit_info = "Not visited"

    if states:
        return f"{states} ({visit_info})"
    return f"({visit_info})"


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


def get_trail_color(
    trail: dict[str, Any], highlighted_trail_id: str | None = None
) -> str:
    """
    Get trail line color based on hiking and highlight status.

    Args:
        trail: Trail dict from API
        highlighted_trail_id: ID of currently highlighted trail (or None)

    Returns:
        CSS color string ('gold' for highlighted, 'green' for hiked, 'gray' for not hiked)
    """
    trail_id = trail.get("trail_id")
    if highlighted_trail_id and trail_id == highlighted_trail_id:
        return "#FFD700"  # Gold for highlighted trail
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


def compute_trail_center(geometry: dict[str, Any]) -> tuple[list[float], int]:
    """
    Compute center point and zoom level from a trail GeoJSON geometry.

    Extracts all coordinates from a LineString or MultiLineString and
    returns the mean lat/lon as the center with a zoom level of 14.

    Args:
        geometry: GeoJSON geometry dict with 'type' and 'coordinates'

    Returns:
        Tuple of ([lat, lon], zoom_level)
    """
    coords: list[tuple[float, float]] = []
    geom_type = geometry.get("type", "")

    if geom_type == "LineString":
        coords = geometry.get("coordinates", [])
    elif geom_type == "MultiLineString":
        for line in geometry.get("coordinates", []):
            coords.extend(line)

    if not coords:
        return [39.8283, -98.5795], 4  # Fallback to US center

    # GeoJSON coordinates are [lon, lat]
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    center_lat = sum(lats) / len(lats)
    center_lon = sum(lons) / len(lons)

    return [center_lat, center_lon], 14

"""
Map component using Folium for interactive trail visualization.

Renders a multi-layer map with:
- Park center markers (visited/unvisited)
- Park boundary polygons
- Trail LineStrings (hiked/not hiked)
- Hiked location points from Google Maps
"""

from typing import Any

import folium
from streamlit_folium import st_folium

from streamlit_app.utils.formatting import (
    format_miles,
    format_park_name,
    format_trail_name,
    get_trail_color,
    get_trail_weight,
    get_visit_status_color,
)


def render_map(
    all_parks: list[dict[str, Any]],
    selected_parks: list[str],
    park_data: dict[str, dict[str, Any]],
    center: list[float],
    zoom: int,
    highlighted_trail_id: str | None = None,
) -> Any:
    """
    Render the interactive Folium map.

    Args:
        all_parks: List of all park dicts from API
        selected_parks: List of selected park codes
        park_data: Dict mapping park_code to {boundary, trails, hiked_points}
        center: [lat, lon] for map center
        zoom: Zoom level
        highlighted_trail_id: Optional trail ID to highlight

    Returns:
        Folium map object rendered via st_folium
    """
    # Create base map
    m = folium.Map(
        location=center,
        zoom_start=zoom,
        tiles="OpenStreetMap",
        control_scale=True,
    )

    # Layer 1: All park center markers (always visible)
    for park in all_parks:
        if not park.get("latitude") or not park.get("longitude"):
            continue

        park_code = park["park_code"]
        is_selected = park_code in selected_parks
        color = get_visit_status_color(park)

        # Create popup content
        popup_html = f"""
        <div style="font-family: sans-serif; min-width: 200px;">
            <h4 style="margin: 0 0 8px 0;">{park.get("full_name", park.get("park_name", "Unknown"))}</h4>
            <p style="margin: 4px 0;"><strong>Code:</strong> {park_code}</p>
            <p style="margin: 4px 0;"><strong>States:</strong> {park.get("states", "N/A")}</p>
        """

        if park.get("visit_month") and park.get("visit_year"):
            popup_html += f"""
            <p style="margin: 4px 0;"><strong>Visited:</strong> {park["visit_month"]} {park["visit_year"]}</p>
            """
        else:
            popup_html += """
            <p style="margin: 4px 0; color: #888;">Not yet visited</p>
            """

        popup_html += "</div>"

        # Add marker
        folium.CircleMarker(
            location=[park["latitude"], park["longitude"]],
            radius=8 if is_selected else 6,
            color="black" if is_selected else color,
            fill=True,
            fillColor=color,
            fillOpacity=0.7 if is_selected else 0.5,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=format_park_name(park),
            weight=2 if is_selected else 1,
        ).add_to(m)

    # Layer 2 & 3: Selected parks' boundaries and trails
    for park_code in selected_parks:
        if park_code not in park_data:
            continue

        data = park_data[park_code]

        # Get park info for metadata
        park = next((p for p in all_parks if p["park_code"] == park_code), None)
        park_name = park.get("park_name", park_code) if park else park_code

        # Draw boundary (if available)
        boundary = data.get("boundary")
        if boundary:
            folium.GeoJson(
                boundary,
                style_function=lambda x: {
                    "fillColor": "lightblue",
                    "color": "blue",
                    "weight": 2,
                    "fillOpacity": 0.2,
                },
                tooltip=f"{park_name} boundary",
            ).add_to(m)

        # Draw trails (if available)
        trails_data = data.get("trails")
        if trails_data and trails_data.get("trails"):
            trails = trails_data["trails"]

            for trail in trails:
                if not trail.get("geometry"):
                    continue

                trail_name = format_trail_name(trail)
                length = trail.get("length_miles", 0)
                hiked = trail.get("hiked", False)

                # Determine styling
                color = get_trail_color(trail)
                weight = get_trail_weight(trail, highlighted_trail_id)
                dash_array = None if hiked else "10, 5"

                # Create popup
                popup_html = f"""
                <div style="font-family: sans-serif; min-width: 180px;">
                    <h4 style="margin: 0 0 8px 0;">{trail_name}</h4>
                    <p style="margin: 4px 0;"><strong>Park:</strong> {park_name}</p>
                    <p style="margin: 4px 0;"><strong>Length:</strong> {format_miles(length)}</p>
                    <p style="margin: 4px 0;"><strong>Source:</strong> {trail.get("source", "N/A")}</p>
                    <p style="margin: 4px 0;"><strong>Hiked:</strong> {"Yes" if hiked else "No"}</p>
                </div>
                """

                # Add trail line
                folium.GeoJson(
                    trail["geometry"],
                    style_function=lambda x, c=color, w=weight, d=dash_array: {
                        "color": c,
                        "weight": w,
                        "opacity": 0.8,
                        "dashArray": d,
                    },
                    popup=folium.Popup(popup_html, max_width=250),
                    tooltip=f"{trail_name} ({format_miles(length)})",
                ).add_to(m)

        # Layer 4: Draw hiked points (if available)
        hiked_points_data = data.get("hiked_points")
        if hiked_points_data and hiked_points_data.get("hiked_points"):
            points = hiked_points_data["hiked_points"]

            for point in points:
                if not point.get("latitude") or not point.get("longitude"):
                    continue

                location_name = point.get("location_name", "Unknown")
                matched_trail = point.get("matched_trail_name")

                popup_html = f"""
                <div style="font-family: sans-serif; min-width: 160px;">
                    <h4 style="margin: 0 0 8px 0;">{location_name}</h4>
                    <p style="margin: 4px 0;"><strong>Park:</strong> {park_name}</p>
                """

                if matched_trail:
                    popup_html += f"""
                    <p style="margin: 4px 0;"><strong>Trail:</strong> {matched_trail}</p>
                    <p style="margin: 4px 0;"><strong>Source:</strong> {point.get("source", "N/A")}</p>
                    """
                else:
                    popup_html += """
                    <p style="margin: 4px 0; color: #888;">Not matched to trail</p>
                    """

                popup_html += "</div>"

                folium.CircleMarker(
                    location=[point["latitude"], point["longitude"]],
                    radius=4,
                    color="red",
                    fill=True,
                    fillColor="orange",
                    fillOpacity=0.6,
                    popup=folium.Popup(popup_html, max_width=220),
                    tooltip=location_name,
                    weight=1,
                ).add_to(m)

    # Render map using streamlit-folium
    output = st_folium(
        m,
        width=None,  # Use full container width
        height=600,
        returned_objects=["last_object_clicked"],
    )

    return output

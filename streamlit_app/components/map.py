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
from folium import MacroElement
from jinja2 import Template
from streamlit_folium import st_folium

from streamlit_app.utils.formatting import (
    format_miles,
    format_park_visit_line,
    format_trail_name,
    get_trail_color,
    get_trail_weight,
    get_visit_status_color,
)

# Default US center and zoom for the initial map view
_US_CENTER = [39.8283, -98.5795]
_US_ZOOM = 4


class _HomeButton(MacroElement):
    """Leaflet control that resets the map to its initial center and zoom."""

    _template = Template("""
        {% macro script(this, kwargs) %}
            (function() {
                var HomeControl = L.Control.extend({
                    options: { position: 'topleft' },
                    onAdd: function(map) {
                        var btn = L.DomUtil.create('div',
                            'leaflet-bar leaflet-control');
                        var a = L.DomUtil.create('a', '', btn);
                        a.href = '#';
                        a.title = 'Reset view';
                        a.role = 'button';
                        a.innerHTML = '&#x1F3E0;';
                        a.style.fontSize = '18px';
                        a.style.lineHeight = '30px';
                        a.style.width = '30px';
                        a.style.height = '30px';
                        a.style.textAlign = 'center';
                        a.style.textDecoration = 'none';
                        a.style.display = 'block';
                        L.DomEvent.on(a, 'click', function(e) {
                            L.DomEvent.stop(e);
                            map.setView(
                                [{{ this.center[0] }}, {{ this.center[1] }}],
                                {{ this.zoom }});
                        });
                        return btn;
                    }
                });
                new HomeControl().addTo({{ this._parent.get_name() }});
            })();
        {% endmacro %}
    """)

    def __init__(self, center: list[float], zoom: int) -> None:
        super().__init__()
        self.center = center
        self.zoom = zoom


def _extract_boundary_line(boundary: dict[str, Any]) -> dict[str, Any] | None:
    """Extract exterior ring(s) from a Polygon/MultiPolygon as a line geometry.

    Returns a LineString (for Polygon) or MultiLineString (for MultiPolygon)
    so that tooltips can be attached to the boundary stroke only,
    not the entire filled polygon area.
    """
    geom_type = boundary.get("type")
    coords = boundary.get("coordinates")
    if not coords:
        return None

    if geom_type == "Polygon":
        return {"type": "LineString", "coordinates": coords[0]}
    if geom_type == "MultiPolygon":
        return {
            "type": "MultiLineString",
            "coordinates": [polygon[0] for polygon in coords],
        }
    return None


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
        tiles="CartoDB Positron",
        control_scale=True,
    )

    # Override Leaflet's default white-space: nowrap on tooltips so that
    # long park names wrap instead of overflowing.
    m.get_root().html.add_child(
        folium.Element(
            "<style>.leaflet-tooltip { white-space: normal; min-width: 200px; max-width: 350px; }</style>"
        )
    )

    # Home button resets to the default US overview
    m.add_child(_HomeButton(center=_US_CENTER, zoom=_US_ZOOM))

    # Layer 1: All park center markers (always visible)
    for park in all_parks:
        if not park.get("latitude") or not park.get("longitude"):
            continue

        park_code = park["park_code"]
        is_selected = park_code in selected_parks
        color = get_visit_status_color(park)

        # Create tooltip content (shown on hover)
        full_name = park.get("full_name", park.get("park_name", "Unknown"))
        visit_line = format_park_visit_line(park)

        tooltip_html = f"""
        <div style="font-family: sans-serif;">
            <h4 style="margin: 0 0 4px 0;">{full_name}</h4>
            <p style="margin: 4px 0; color: #555;">{visit_line}</p>
        </div>"""

        # Determine icon style based on visit and selection status
        if is_selected:
            icon = folium.Icon(color="darkgreen", icon="ok-sign")
        elif color == "green":
            icon = folium.Icon(color="green", icon="info-sign")
        else:
            icon = folium.Icon(color="lightgray", icon="info-sign")

        # Add teardrop pin marker (tooltip on hover, no popup)
        folium.Marker(
            location=[park["latitude"], park["longitude"]],
            tooltip=folium.Tooltip(tooltip_html, sticky=False),
            icon=icon,
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
        # Split into two layers: a filled polygon (no tooltip) and a
        # boundary line (with tooltip) so the tooltip only appears when
        # hovering over the actual border, not anywhere inside the park.
        boundary = data.get("boundary")
        if boundary:
            folium.GeoJson(
                boundary,
                style_function=lambda x: {
                    "fillColor": "lightblue",
                    "color": "transparent",
                    "weight": 0,
                    "fillOpacity": 0.2,
                },
            ).add_to(m)

            boundary_line = _extract_boundary_line(boundary)
            if boundary_line:
                folium.GeoJson(
                    boundary_line,
                    style_function=lambda x: {
                        "color": "blue",
                        "weight": 2,
                        "opacity": 1,
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
                color = get_trail_color(trail, highlighted_trail_id)
                weight = get_trail_weight(trail, highlighted_trail_id)
                is_highlighted = (
                    highlighted_trail_id
                    and trail.get("trail_id") == highlighted_trail_id
                )
                dash_array = None if (hiked or is_highlighted) else "10, 5"

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

"""
Export utilities for converting trail data to various formats.

Provides functions to export trail data as CSV or GeoJSON files.
"""

import csv
import json
from io import StringIO
from typing import Any


def trails_to_csv(trails: list[dict[str, Any]]) -> str:
    """
    Convert trails list to CSV format.

    Args:
        trails: List of trail dictionaries

    Returns:
        CSV string content
    """
    if not trails:
        return ""

    # Define CSV columns
    columns = [
        "trail_name",
        "park_code",
        "park_name",
        "length_mi",
        "source",
        "trail_type",
        "hiked",
        "viz_3d",
    ]

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()

    for trail in trails:
        # Convert boolean values to strings
        row = {
            **trail,
            "hiked": "Yes" if trail.get("hiked") else "No",
            "viz_3d": "Yes" if trail.get("viz_3d") else "No",
        }
        writer.writerow(row)

    return output.getvalue()


def trails_to_geojson(trails: list[dict[str, Any]]) -> str:
    """
    Convert trails list to GeoJSON format.

    Args:
        trails: List of trail dictionaries with geometry

    Returns:
        GeoJSON string content
    """
    if not trails:
        return json.dumps({"type": "FeatureCollection", "features": []})

    features = []
    for trail in trails:
        geometry = trail.get("geometry")
        if not geometry:
            continue

        # Create feature with properties
        feature = {
            "type": "Feature",
            "geometry": geometry,
            "properties": {
                "trail_name": trail.get("trail_name"),
                "park_code": trail.get("park_code"),
                "park_name": trail.get("park_name"),
                "length_mi": trail.get("length_mi"),
                "source": trail.get("source"),
                "trail_type": trail.get("trail_type"),
                "hiked": trail.get("hiked", False),
                "viz_3d": trail.get("viz_3d", False),
            },
        }
        features.append(feature)

    geojson = {
        "type": "FeatureCollection",
        "features": features,
    }

    return json.dumps(geojson, indent=2)

"""
Database query functions for the API.

These functions execute SQL queries and return formatted results
ready for API responses.
"""

from typing import Any

from sqlalchemy import text

from api.database import get_db_engine


def fetch_trails_for_park(
    park_code: str,
    min_length: float | None = None,
    max_length: float | None = None,
    trail_type: str | None = None,
) -> dict[str, Any]:
    """
    Fetch trails from database for a specific park with optional filters.

    Args:
        park_code: 4-character lowercase park code (e.g., 'yose')
        min_length: Minimum trail length in miles (optional)
        max_length: Maximum trail length in miles (optional)
        trail_type: OSM highway type filter (e.g., 'path', 'footway') (optional)

    Returns:
        Dictionary containing:
            - park_code: str
            - park_name: str or None
            - trail_count: int
            - total_miles: float
            - trails: list of trail dictionaries

    Example:
        >>> fetch_trails_for_park('yose', min_length=3, max_length=5)
        {
            'park_code': 'yose',
            'park_name': 'Yosemite National Park',
            'trail_count': 12,
            'total_miles': 48.3,
            'trails': [...]
        }
    """
    engine = get_db_engine()

    # Base query joining osm_hikes with parks table
    query = """
    SELECT
        oh.osm_id,
        oh.name,
        oh.length_miles,
        oh.highway as highway_type,
        'osm' as source,
        oh.geometry_type,
        p.park_name
    FROM osm_hikes oh
    LEFT JOIN parks p ON oh.park_code = p.park_code
    WHERE oh.park_code = :park_code
    """

    # Build dynamic WHERE clauses based on optional filters
    params: dict[str, Any] = {"park_code": park_code}

    if min_length is not None:
        query += " AND oh.length_miles >= :min_length"
        params["min_length"] = min_length

    if max_length is not None:
        query += " AND oh.length_miles <= :max_length"
        params["max_length"] = max_length

    if trail_type is not None:
        query += " AND oh.highway = :trail_type"
        params["trail_type"] = trail_type

    # Order by length descending (longest trails first)
    query += " ORDER BY oh.length_miles DESC"

    # Execute query
    with engine.connect() as conn:
        result = conn.execute(text(query), params)
        rows = result.fetchall()

    # Handle case where no trails found
    if not rows:
        return {
            "park_code": park_code,
            "park_name": None,
            "trail_count": 0,
            "total_miles": 0.0,
            "trails": [],
        }

    # Get park name from first row (same for all rows)
    park_name = rows[0].park_name if rows else None

    # Format trails and calculate total mileage
    trails = []
    total_miles = 0.0

    for row in rows:
        trail = {
            "osm_id": row.osm_id,
            "name": row.name,
            "length_miles": float(row.length_miles),
            "highway_type": row.highway_type,
            "source": row.source,
            "geometry_type": row.geometry_type,
        }
        trails.append(trail)
        total_miles += float(row.length_miles)

    return {
        "park_code": park_code,
        "park_name": park_name,
        "trail_count": len(trails),
        "total_miles": round(total_miles, 2),
        "trails": trails,
    }

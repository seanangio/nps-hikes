"""
Database query functions for the API.

These functions execute SQL queries and return formatted results
ready for API responses.
"""

from typing import Any

from sqlalchemy import text

from api.database import get_db_engine


def fetch_all_parks(
    include_description: bool = False,
    visited: bool | None = None,
) -> dict[str, Any]:
    """
    Fetch all parks from the database with optional visit status filtering.

    Args:
        include_description: Whether to include park descriptions (default: False)
        visited: Filter by visit status. True=visited only, False=unvisited only,
                 None=all parks (default: None)

    Returns:
        Dictionary containing:
            - park_count: int (number of parks returned)
            - visited_count: int (number of visited parks in the result)
            - parks: list of park dictionaries

    Example:
        >>> fetch_all_parks()
        {
            'park_count': 63,
            'visited_count': 36,
            'parks': [...]
        }
    """
    engine = get_db_engine()

    # Build column list based on include_description parameter
    columns = [
        "park_code",
        "park_name",
        "full_name",
        "designation",
        "states",
        "latitude",
        "longitude",
        "url",
        "visit_month",
        "visit_year",
    ]

    if include_description:
        columns.append("description")

    columns_str = ", ".join(columns)

    # Build WHERE clause based on visited filter
    where_clauses = []
    if visited is True:
        where_clauses.append("visit_year IS NOT NULL")
    elif visited is False:
        where_clauses.append("visit_year IS NULL")

    where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    # Query parks ordered by park name
    query = f"""
    SELECT {columns_str}
    FROM parks
    {where_str}
    ORDER BY park_name
    """

    # Execute query
    with engine.connect() as conn:
        result = conn.execute(text(query))
        rows = result.fetchall()

    # Format parks
    parks = []
    visited_count = 0
    for row in rows:
        park = {
            "park_code": row.park_code,
            "park_name": row.park_name,
            "full_name": row.full_name,
            "designation": row.designation,
            "states": row.states,
            "latitude": float(row.latitude) if row.latitude is not None else None,
            "longitude": float(row.longitude) if row.longitude is not None else None,
            "url": row.url,
            "visit_month": row.visit_month,
            "visit_year": row.visit_year,
        }

        if row.visit_year is not None:
            visited_count += 1

        if include_description:
            park["description"] = row.description

        parks.append(park)

    return {
        "park_count": len(parks),
        "visited_count": visited_count,
        "parks": parks,
    }


def fetch_trails(
    park_code: str | None = None,
    min_length: float | None = None,
    max_length: float | None = None,
    state: str | None = None,
    source: str | None = None,
    hiked: bool | None = None,
    trail_type: str | None = None,
    viz_3d: bool | None = None,
) -> dict[str, Any]:
    """
    Fetch trails with optional filters.

    Combines TNM and OSM trail data, preferring TNM when duplicates exist
    (based on fuzzy name matching within the same park).

    Args:
        park_code: Filter by specific park code (e.g., 'yose') (optional)
        min_length: Minimum trail length in miles (optional)
        max_length: Maximum trail length in miles (optional)
        state: Filter trails in parks containing this state (e.g., 'CA') (optional)
        source: Filter by data source ('TNM' or 'OSM') (optional)
        hiked: Filter by hiking status - True for hiked, False for not hiked, None for all (optional)
        trail_type: OSM highway type filter (e.g., 'path', 'footway') (optional)
        viz_3d: Filter by 3D visualization availability (optional)

    Returns:
        Dictionary containing:
            - trail_count: int
            - total_miles: float
            - trails: list of trail dictionaries

    Example:
        >>> fetch_trails(park_code='yose', min_length=3, max_length=5)
        {
            'trail_count': 12,
            'total_miles': 48.3,
            'trails': [...]
        }
    """
    engine = get_db_engine()

    # Build query with CTEs for TNM trails, OSM trails, and deduplication
    query = """
    WITH tnm_trails AS (
        SELECT
            permanent_identifier as trail_id,
            name as trail_name,
            park_code,
            'TNM' as source,
            length_miles,
            geometry_type
        FROM tnm_hikes
        WHERE name IS NOT NULL
    ),
    osm_trails AS (
        SELECT
            osm_id::text as trail_id,
            name as trail_name,
            park_code,
            'OSM' as source,
            length_miles,
            geometry_type,
            highway as highway_type
        FROM osm_hikes
        WHERE name IS NOT NULL
    ),
    -- Find OSM trails that don't match TNM (deduplication via fuzzy matching)
    osm_unique AS (
        SELECT o.*
        FROM osm_trails o
        WHERE NOT EXISTS (
            SELECT 1
            FROM tnm_trails t
            WHERE t.park_code = o.park_code
            AND similarity(lower(t.trail_name), lower(o.trail_name)) > 0.7
        )
    ),
    -- Combine TNM (preferred) + unique OSM trails
    all_trails AS (
        SELECT
            trail_id,
            trail_name,
            park_code,
            source,
            length_miles,
            geometry_type,
            CAST(NULL AS VARCHAR) as highway_type
        FROM tnm_trails
        UNION ALL
        SELECT * FROM osm_unique
    )
    SELECT
        t.trail_id,
        t.trail_name,
        t.park_code,
        p.park_name,
        p.states,
        t.source,
        t.length_miles,
        t.geometry_type,
        t.highway_type,
        CASE
            WHEN m.gmaps_location_id IS NOT NULL THEN true
            ELSE false
        END as hiked,
        CASE
            WHEN ute.trail_slug IS NOT NULL THEN true
            ELSE false
        END as viz_3d_available,
        ute.trail_slug as viz_3d_slug
    FROM all_trails t
    LEFT JOIN parks p ON t.park_code = p.park_code
    LEFT JOIN gmaps_hiking_locations_matched m
        ON t.park_code = m.park_code
        AND t.source = m.source
        AND t.trail_name = m.matched_trail_name
    LEFT JOIN usgs_trail_elevations ute
        ON m.gmaps_location_id = ute.gmaps_location_id
    WHERE 1=1
    """

    # Build dynamic WHERE clauses based on optional filters
    params: dict[str, Any] = {}

    if park_code is not None:
        query += " AND t.park_code = :park_code"
        params["park_code"] = park_code

    if min_length is not None:
        query += " AND t.length_miles >= :min_length"
        params["min_length"] = min_length

    if max_length is not None:
        query += " AND t.length_miles <= :max_length"
        params["max_length"] = max_length

    if state is not None:
        query += " AND p.states LIKE :state"
        params["state"] = f"%{state}%"

    if source is not None:
        query += " AND t.source = :source"
        params["source"] = source

    if hiked is not None:
        if hiked:
            query += " AND m.gmaps_location_id IS NOT NULL"
        else:
            query += " AND m.gmaps_location_id IS NULL"

    if trail_type is not None:
        query += " AND t.highway_type = :trail_type"
        params["trail_type"] = trail_type

    if viz_3d is not None:
        if viz_3d:
            query += " AND ute.trail_slug IS NOT NULL"
        else:
            query += " AND ute.trail_slug IS NULL"

    # Sort by length descending for single-park queries, by park/name otherwise
    if park_code is not None:
        query += " ORDER BY t.length_miles DESC"
    else:
        query += " ORDER BY t.park_code, t.trail_name"

    # Execute query
    with engine.connect() as conn:
        result = conn.execute(text(query), params)
        rows = result.fetchall()

    # Format trails and calculate total mileage
    trails = []
    total_miles = 0.0

    for row in rows:
        trail = {
            "trail_id": row.trail_id,
            "trail_name": row.trail_name,
            "park_code": row.park_code,
            "park_name": row.park_name,
            "states": row.states,
            "source": row.source,
            "length_miles": float(row.length_miles),
            "geometry_type": row.geometry_type,
            "highway_type": row.highway_type,
            "hiked": row.hiked,
            "viz_3d_available": row.viz_3d_available,
            "viz_3d_slug": row.viz_3d_slug,
        }
        trails.append(trail)
        total_miles += float(row.length_miles)

    return {
        "trail_count": len(trails),
        "total_miles": round(total_miles, 2),
        "trails": trails,
    }

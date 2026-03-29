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
    visit_year: int | None = None,
    visit_month: list[str] | None = None,
) -> dict[str, Any]:
    """
    Fetch all parks from the database with optional filtering.

    Args:
        include_description: Whether to include park descriptions (default: False)
        visited: Filter by visit status. True=visited only, False=unvisited only,
                 None=all parks (default: None)
        visit_year: Filter by visit year (e.g., 2024). Default: None (no filter)
        visit_month: Filter by visit month(s). Accepts a list of month strings
                     to match against the database (e.g., ["Oct", "October"]).
                     Default: None (no filter)

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

    # Build WHERE clause and query parameters
    where_clauses: list[str] = []
    query_params: dict[str, Any] = {}

    if visited is True:
        where_clauses.append("visit_year IS NOT NULL")
    elif visited is False:
        where_clauses.append("visit_year IS NULL")

    if visit_year is not None:
        where_clauses.append("visit_year = :visit_year")
        query_params["visit_year"] = visit_year

    if visit_month:
        month_placeholders = ", ".join(f":month_{i}" for i in range(len(visit_month)))
        where_clauses.append(f"visit_month IN ({month_placeholders})")
        for i, m in enumerate(visit_month):
            query_params[f"month_{i}"] = m

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
        result = conn.execute(text(query), query_params)
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
    limit: int = 50,
    offset: int = 0,
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
        ute.trail_slug as viz_3d_slug,
        COUNT(*) OVER() as total_count
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

    # Add pagination
    query += " LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset

    # Execute query
    with engine.connect() as conn:
        result = conn.execute(text(query), params)
        rows = result.fetchall()

    # Extract total_count from first row (or 0 if no results)
    total_count = rows[0].total_count if rows else 0

    # Format trails and calculate total mileage for this page
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
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total_count": total_count,
            "has_next": (offset + limit) < total_count,
            "has_prev": offset > 0,
        },
    }


def fetch_stats(hiked: bool | None = None) -> dict[str, Any]:
    """
    Fetch aggregate hiking statistics.

    Computes summary statistics across all deduplicated trails, optionally
    filtered by hiking status.

    Args:
        hiked: Filter by hiking status. True=hiked only, False=not hiked only,
               None=all trails (default: None)

    Returns:
        Dictionary containing:
            - total_trails: int
            - total_miles: float
            - avg_trail_length: float
            - parks_count: int
            - states_count: int
            - source_breakdown: dict with tnm and osm counts
            - longest_trail: dict or None
            - shortest_trail: dict or None
    """
    engine = get_db_engine()

    query = """
    WITH tnm_trails AS (
        SELECT
            name as trail_name,
            park_code,
            'TNM' as source,
            length_miles
        FROM tnm_hikes
        WHERE name IS NOT NULL
    ),
    osm_trails AS (
        SELECT
            name as trail_name,
            park_code,
            'OSM' as source,
            length_miles
        FROM osm_hikes
        WHERE name IS NOT NULL
    ),
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
    all_trails AS (
        SELECT * FROM tnm_trails
        UNION ALL
        SELECT * FROM osm_unique
    ),
    filtered AS (
        SELECT t.trail_name, t.park_code, t.source, t.length_miles,
               p.park_name, p.states
        FROM all_trails t
        LEFT JOIN parks p ON t.park_code = p.park_code
        LEFT JOIN gmaps_hiking_locations_matched m
            ON t.park_code = m.park_code
            AND t.source = m.source
            AND t.trail_name = m.matched_trail_name
        WHERE 1=1
    """

    params: dict[str, Any] = {}

    if hiked is not None:
        if hiked:
            query += " AND m.gmaps_location_id IS NOT NULL"
        else:
            query += " AND m.gmaps_location_id IS NULL"

    query += """
    ),
    stats AS (
        SELECT
            COUNT(*) as total_trails,
            COALESCE(SUM(length_miles), 0) as total_miles,
            COALESCE(AVG(length_miles), 0) as avg_trail_length,
            COUNT(DISTINCT park_code) as parks_count,
            COUNT(*) FILTER (WHERE source = 'TNM') as tnm_count,
            COUNT(*) FILTER (WHERE source = 'OSM') as osm_count
        FROM filtered
    ),
    longest AS (
        SELECT trail_name, park_code, park_name, length_miles
        FROM filtered
        ORDER BY length_miles DESC
        LIMIT 1
    ),
    shortest AS (
        SELECT trail_name, park_code, park_name, length_miles
        FROM filtered
        ORDER BY length_miles ASC
        LIMIT 1
    ),
    distinct_states AS (
        SELECT COUNT(DISTINCT trim(s)) as states_count
        FROM filtered, unnest(string_to_array(states, ',')) as s
    )
    SELECT
        s.total_trails, s.total_miles, s.avg_trail_length, s.parks_count,
        s.tnm_count, s.osm_count,
        ds.states_count,
        l.trail_name as longest_trail_name,
        l.park_code as longest_park_code,
        l.park_name as longest_park_name,
        l.length_miles as longest_length_miles,
        sh.trail_name as shortest_trail_name,
        sh.park_code as shortest_park_code,
        sh.park_name as shortest_park_name,
        sh.length_miles as shortest_length_miles
    FROM stats s
    CROSS JOIN distinct_states ds
    LEFT JOIN longest l ON true
    LEFT JOIN shortest sh ON true
    """

    with engine.connect() as conn:
        result = conn.execute(text(query), params)
        row = result.fetchone()

    if not row or row.total_trails == 0:
        return {
            "total_trails": 0,
            "total_miles": 0.0,
            "avg_trail_length": 0.0,
            "parks_count": 0,
            "states_count": 0,
            "source_breakdown": {"tnm": 0, "osm": 0},
            "longest_trail": None,
            "shortest_trail": None,
        }

    longest_trail = None
    if row.longest_trail_name is not None:
        longest_trail = {
            "trail_name": row.longest_trail_name,
            "park_code": row.longest_park_code,
            "park_name": row.longest_park_name,
            "length_miles": float(row.longest_length_miles),
        }

    shortest_trail = None
    if row.shortest_trail_name is not None:
        shortest_trail = {
            "trail_name": row.shortest_trail_name,
            "park_code": row.shortest_park_code,
            "park_name": row.shortest_park_name,
            "length_miles": float(row.shortest_length_miles),
        }

    return {
        "total_trails": row.total_trails,
        "total_miles": round(float(row.total_miles), 2),
        "avg_trail_length": round(float(row.avg_trail_length), 2),
        "parks_count": row.parks_count,
        "states_count": row.states_count,
        "source_breakdown": {
            "tnm": row.tnm_count,
            "osm": row.osm_count,
        },
        "longest_trail": longest_trail,
        "shortest_trail": shortest_trail,
    }


def fetch_park_stats(hiked: bool | None = None) -> dict[str, Any]:
    """
    Fetch per-park hiking statistics.

    Computes trail statistics grouped by park, optionally filtered
    by hiking status.

    Args:
        hiked: Filter by hiking status. True=hiked only, False=not hiked only,
               None=all trails (default: None)

    Returns:
        Dictionary containing:
            - park_count: int
            - parks: list of per-park stat dictionaries
    """
    engine = get_db_engine()

    query = """
    WITH tnm_trails AS (
        SELECT
            name as trail_name,
            park_code,
            'TNM' as source,
            length_miles
        FROM tnm_hikes
        WHERE name IS NOT NULL
    ),
    osm_trails AS (
        SELECT
            name as trail_name,
            park_code,
            'OSM' as source,
            length_miles
        FROM osm_hikes
        WHERE name IS NOT NULL
    ),
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
    all_trails AS (
        SELECT * FROM tnm_trails
        UNION ALL
        SELECT * FROM osm_unique
    ),
    filtered AS (
        SELECT t.trail_name, t.park_code, t.source, t.length_miles,
               p.park_name
        FROM all_trails t
        LEFT JOIN parks p ON t.park_code = p.park_code
        LEFT JOIN gmaps_hiking_locations_matched m
            ON t.park_code = m.park_code
            AND t.source = m.source
            AND t.trail_name = m.matched_trail_name
        WHERE 1=1
    """

    params: dict[str, Any] = {}

    if hiked is not None:
        if hiked:
            query += " AND m.gmaps_location_id IS NOT NULL"
        else:
            query += " AND m.gmaps_location_id IS NULL"

    query += """
    )
    SELECT
        park_code,
        park_name,
        COUNT(*) as trail_count,
        COALESCE(SUM(length_miles), 0) as total_miles,
        COALESCE(AVG(length_miles), 0) as avg_trail_length
    FROM filtered
    GROUP BY park_code, park_name
    ORDER BY trail_count DESC, total_miles DESC
    """

    with engine.connect() as conn:
        result = conn.execute(text(query), params)
        rows = result.fetchall()

    parks = []
    for row in rows:
        parks.append(
            {
                "park_code": row.park_code,
                "park_name": row.park_name,
                "trail_count": row.trail_count,
                "total_miles": round(float(row.total_miles), 2),
                "avg_trail_length": round(float(row.avg_trail_length), 2),
            }
        )

    return {
        "park_count": len(parks),
        "parks": parks,
    }


def fetch_park_summary(park_code: str) -> dict[str, Any] | None:
    """
    Fetch a detailed summary for a single park.

    Combines park metadata with trail statistics including hiked counts,
    source breakdown, and 3D visualization availability.

    Args:
        park_code: 4-character lowercase park code (e.g., 'yose')

    Returns:
        Dictionary with park metadata and trail statistics, or None if
        the park is not found.
    """
    engine = get_db_engine()

    query = """
    WITH tnm_trails AS (
        SELECT
            name as trail_name,
            park_code,
            'TNM' as source,
            length_miles
        FROM tnm_hikes
        WHERE name IS NOT NULL
    ),
    osm_trails AS (
        SELECT
            name as trail_name,
            park_code,
            'OSM' as source,
            length_miles
        FROM osm_hikes
        WHERE name IS NOT NULL
    ),
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
    all_trails AS (
        SELECT * FROM tnm_trails
        UNION ALL
        SELECT * FROM osm_unique
    ),
    trail_stats AS (
        SELECT
            COUNT(*) as total_trails,
            COALESCE(SUM(t.length_miles), 0) as total_miles,
            COALESCE(AVG(t.length_miles), 0) as avg_trail_length,
            COUNT(*) FILTER (WHERE m.gmaps_location_id IS NOT NULL) as hiked_trails,
            COALESCE(SUM(t.length_miles) FILTER (WHERE m.gmaps_location_id IS NOT NULL), 0) as hiked_miles,
            COUNT(*) FILTER (WHERE t.source = 'TNM') as tnm_count,
            COUNT(*) FILTER (WHERE t.source = 'OSM') as osm_count,
            COUNT(*) FILTER (WHERE ute.trail_slug IS NOT NULL) as viz_3d_count
        FROM all_trails t
        LEFT JOIN gmaps_hiking_locations_matched m
            ON t.park_code = m.park_code
            AND t.source = m.source
            AND t.trail_name = m.matched_trail_name
        LEFT JOIN usgs_trail_elevations ute
            ON m.gmaps_location_id = ute.gmaps_location_id
        WHERE t.park_code = :park_code
    )
    SELECT
        p.park_code, p.park_name, p.full_name, p.designation, p.states,
        p.latitude, p.longitude, p.url, p.visit_month, p.visit_year,
        ts.total_trails, ts.total_miles, ts.avg_trail_length,
        ts.hiked_trails, ts.hiked_miles,
        ts.tnm_count, ts.osm_count,
        ts.viz_3d_count
    FROM parks p
    CROSS JOIN trail_stats ts
    WHERE p.park_code = :park_code
    """

    with engine.connect() as conn:
        result = conn.execute(text(query), {"park_code": park_code})
        row = result.fetchone()

    if not row:
        return None

    return {
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
        "total_trails": row.total_trails,
        "total_miles": round(float(row.total_miles), 2),
        "avg_trail_length": round(float(row.avg_trail_length), 2),
        "hiked_trails": row.hiked_trails,
        "hiked_miles": round(float(row.hiked_miles), 2),
        "source_breakdown": {
            "tnm": row.tnm_count,
            "osm": row.osm_count,
        },
        "viz_3d_count": row.viz_3d_count,
    }

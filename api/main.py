"""
NPS Trails API

A FastAPI application that provides access to National Park trail data
collected from OpenStreetMap and USGS.

This API exposes analytical outputs from the NPS Hikes project, allowing
users to query trail information without needing to run the collection pipeline.

Usage:
    Start the development server:
        $ uvicorn api.main:app --reload

    The API will be available at:
        - Interactive docs (Swagger UI): http://localhost:8000/docs
        - Alternative docs (ReDoc): http://localhost:8000/redoc
        - OpenAPI schema: http://localhost:8000/openapi.json
"""

import os
import sys

from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.responses import FileResponse
from sqlalchemy import text

# Add parent directory to path to import project modules
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from api.database import get_db_engine
from api.models import Park, ParksResponse, TrailsResponse
from api.queries import fetch_all_parks, fetch_trails

# Create FastAPI app with metadata for OpenAPI documentation
app = FastAPI(
    title="NPS Hikes API",
    description="""
    API for exploring National Park hiking trails from OpenStreetMap and USGS data sources.

    See the [full project documentation](https://seanangio.github.io/nps-hikes/) for details.
    """,
    version="0.1.0",
    contact={
        "name": "NPS Hikes Project",
    },
    license_info={
        "name": "CC BY-NC-SA 4.0",
        "url": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
    },
)


@app.get("/", tags=["Root"])
async def root():
    """
    Root endpoint returning API information and available endpoints.

    Returns basic metadata about the API and links to documentation.
    """
    return {
        "name": "NPS Trails API",
        "version": "0.1.0",
        "description": "Query National Park trail data from OpenStreetMap and The National Map",
        "documentation": {
            "swagger_ui": "/docs",
            "redoc": "/redoc",
            "openapi_json": "/openapi.json",
        },
        "endpoints": {
            "parks": "/parks",
            "trails": "/trails",
            "us_static_park_map": "/parks/viz/us-static-park-map",
            "us_interactive_park_map": "/parks/viz/us-interactive-park-map",
            "static_map": "/parks/{park_code}/viz/static-map",
            "elevation_matrix": "/parks/{park_code}/viz/elevation-matrix",
            "trail_3d_viz": "/parks/{park_code}/trails/{trail_slug}/viz/3d",
            "health_check": "/health",
        },
    }


@app.get(
    "/parks",
    response_model=ParksResponse,
    response_model_exclude_none=True,
    tags=["Parks"],
    summary="Get all parks",
    description="""
    Returns all National Parks with metadata and optional visit status filtering.

    By default, returns all parks. Use `visited=true` to get only visited parks,
    or `visited=false` to get only unvisited parks.
    Use `include_description=true` to include full park descriptions.
    """,
)
async def get_all_parks(
    include_description: bool = Query(
        default=False,
        description="Include full park descriptions in the response (increases response size)",
    ),
    visited: bool | None = Query(
        default=None,
        description="Filter by visit status: true=visited only, false=not yet visited, omit=all parks",
    ),
):
    """
    Get all parks with metadata.

    Returns a list of all National Parks, including:
    - Park codes (used in other endpoints)
    - Park names, designations, and locations
    - Coordinates (latitude/longitude)
    - Visit dates (month/year, if visited)
    - NPS website URLs
    - Descriptions (optional, excluded by default)

    **Example queries:**
    - All parks: `/parks`
    - Only visited parks: `/parks?visited=true`
    - Unvisited parks: `/parks?visited=false`
    - All parks with descriptions: `/parks?include_description=true`

    **Use cases:**
    - Get park codes for use in other endpoints (trails, visualizations)
    - Build a progress map of all national parks
    - Display a list of parks with visit dates
    """
    try:
        # Fetch parks from database
        result = fetch_all_parks(
            include_description=include_description,
            visited=visited,
        )
        return result

    except Exception as e:
        # Catch any errors and return 500
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving parks: {str(e)}",
        )


@app.get(
    "/trails",
    response_model=TrailsResponse,
    tags=["Trails"],
    summary="Get trails",
    description="""
    Returns hiking trails from both TNM and OSM data sources.

    Combines TNM and OSM data, preferring TNM when duplicates exist (based on fuzzy name matching).
    Supports filtering by park, state, length, source, hiking status, trail type,
    and 3D visualization availability.
    """,
)
async def get_trails(
    park_code: str | None = Query(
        default=None,
        description="Filter by 4-character park code (e.g., 'yose')",
        min_length=4,
        max_length=4,
        pattern="^[a-z]{4}$",
    ),
    state: str | None = Query(
        default=None,
        description="Filter by state using 2-letter code (e.g., 'CA' or 'UT'). For multiple states, repeat the parameter: ?state=CA&state=OR",
        min_length=2,
        max_length=2,
        pattern="^[A-Z]{2}$",
    ),
    source: str | None = Query(
        default=None,
        description="Filter by data source ('TNM' or 'OSM')",
        pattern="^(TNM|OSM)$",
    ),
    hiked: bool | None = Query(
        default=None,
        description="Filter by hiking status. Use true to show only hiked trails, false to show only trails not yet hiked, or omit to show all trails",
    ),
    min_length: float | None = Query(
        default=None,
        description="Minimum trail length in miles (e.g., 5.0)",
        ge=0,
        le=100,
    ),
    max_length: float | None = Query(
        default=None,
        description="Maximum trail length in miles (e.g., 10.0)",
        ge=0,
        le=100,
    ),
    trail_type: str | None = Query(
        default=None,
        description="Filter by OSM highway type (e.g., 'path', 'footway', 'track')",
    ),
    viz_3d: bool | None = Query(
        default=None,
        description="Filter by 3D visualization availability. Use true to show only trails with 3D viz, false to show only trails without 3D viz, or omit to show all trails",
    ),
):
    """
    Get trails with optional filters.

    Returns all trails by default, or a filtered subset. Use `park_code` to scope
    to a single park, `state` to filter by state, or combine any filters.

    This endpoint combines trail data from The National Map (TNM) and OpenStreetMap (OSM),
    automatically deduplicating trails that appear in both sources (TNM is preferred).

    **Deduplication Logic:**
    - Trails with similar names (>70% similarity) in the same park are deduplicated
    - TNM trails are preferred over OSM when duplicates are detected
    - Each trail is marked with its source ('TNM' or 'OSM')

    **Example queries:**
    - All trails: `/trails`
    - Yosemite trails: `/trails?park_code=yose`
    - Trails I've hiked: `/trails?hiked=true`
    - Long trails (>10 miles): `/trails?min_length=10`
    - California trails: `/trails?state=CA`
    - Yosemite trails from TNM: `/trails?park_code=yose&source=TNM`
    - Trails I haven't hiked yet in Utah: `/trails?state=UT&hiked=false`
    - Only footway trails: `/trails?trail_type=footway`
    - Trails with 3D viz: `/trails?viz_3d=true`
    """
    try:
        # Fetch trails from database
        result = fetch_trails(
            park_code=park_code,
            state=state,
            source=source,
            hiked=hiked,
            min_length=min_length,
            max_length=max_length,
            trail_type=trail_type,
            viz_3d=viz_3d,
        )

        return result

    except Exception as e:
        # Catch any errors and return 500
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving trails: {str(e)}",
        )


@app.get(
    "/parks/viz/us-static-park-map",
    tags=["Visualizations"],
    summary="Get static US park map",
    description="""
    Returns a PNG image showing all national parks on a US map with AK/HI insets.

    Parks are color-coded by visited/unvisited status with a visit count legend.
    """,
    responses={
        200: {
            "content": {"image/png": {}},
            "description": "PNG image of US park map",
        },
        404: {"description": "Visualization not available"},
    },
)
async def get_us_static_park_map():
    """
    Get static US park map showing visited and unvisited parks.

    Returns a PNG image with an Albers Equal Area projection and AK/HI insets.

    **Example usage:**
    - `/parks/viz/us-static-park-map`
    """
    viz_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "profiling_results",
        "visualizations",
        "us_park_map",
    )
    file_path = os.path.join(viz_dir, "us_park_map_static.png")

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404,
            detail="US static park map not available. Run the us_park_map profiling module to generate it.",
        )

    return FileResponse(
        file_path,
        media_type="image/png",
    )


@app.get(
    "/parks/viz/us-interactive-park-map",
    tags=["Visualizations"],
    summary="Get interactive US park map",
    description="""
    Returns an interactive HTML map showing all national parks with boundaries and hover tooltips.

    Parks are color-coded by visited/unvisited status. The map is zoomable and pannable.
    """,
    responses={
        200: {
            "content": {"text/html": {}},
            "description": "Interactive HTML park map",
        },
        404: {"description": "Visualization not available"},
    },
)
async def get_us_interactive_park_map():
    """
    Get interactive US park map with boundaries and hover tooltips.

    Returns an HTML page with a zoomable Plotly map.

    **Example usage:**
    - `/parks/viz/us-interactive-park-map`
    """
    viz_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "profiling_results",
        "visualizations",
        "us_park_map",
    )
    file_path = os.path.join(viz_dir, "us_park_map_interactive.html")

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404,
            detail="US interactive park map not available. Run the us_park_map profiling module to generate it.",
        )

    return FileResponse(
        file_path,
        media_type="text/html",
    )


@app.get(
    "/parks/{park_code}/viz/static-map",
    tags=["Visualizations"],
    summary="Get static trail map for a park",
    description="""
    Returns a PNG image showing all trails for the specified park on a static map.

    The map displays trail routes overlaid on the park boundary, providing a visual
    overview of the park's trail network.
    """,
    responses={
        200: {
            "content": {"image/png": {}},
            "description": "PNG image of park trail map",
        },
        404: {"description": "Park not found or visualization not available"},
    },
)
async def get_static_map(
    park_code: str = Path(
        ...,
        description="4-character lowercase park code (e.g., 'yose' for Yosemite)",
        min_length=4,
        max_length=4,
        pattern="^[a-z]{4}$",
        examples=["yose", "grca", "zion"],
    ),
):
    """
    Get static trail map visualization for a park.

    Returns a PNG image showing the park's trail network on a static map background.
    The visualization includes park boundaries and all collected trails.

    **Example usage:**
    - Yosemite map: `/parks/yose/viz/static-map`
    - Grand Canyon map: `/parks/grca/viz/static-map`

    **Use cases:**
    - Embed park trail maps in web applications
    - Download maps for offline reference
    - Generate park trail overviews
    """
    # Construct file path
    viz_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "profiling_results",
        "visualizations",
        "static_maps",
    )
    file_path = os.path.join(viz_dir, f"{park_code}_trails.png")

    # Check if file exists
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404,
            detail=f"Static map not found for park code '{park_code}'. The park may not exist or visualization has not been generated.",
        )

    # Return PNG file (inline display, not download)
    return FileResponse(
        file_path,
        media_type="image/png",
    )


@app.get(
    "/parks/{park_code}/viz/elevation-matrix",
    tags=["Visualizations"],
    summary="Get elevation change matrix for a park",
    description="""
    Returns a PNG heatmap showing elevation changes between different trail points in the park.

    The matrix visualizes elevation gain/loss patterns across the trail network,
    helping identify challenging trail segments and elevation profiles.
    """,
    responses={
        200: {
            "content": {"image/png": {}},
            "description": "PNG image of elevation change matrix",
        },
        404: {"description": "Park not found or visualization not available"},
    },
)
async def get_elevation_matrix(
    park_code: str = Path(
        ...,
        description="4-character lowercase park code (e.g., 'yose' for Yosemite)",
        min_length=4,
        max_length=4,
        pattern="^[a-z]{4}$",
        examples=["yose", "grca", "zion"],
    ),
):
    """
    Get elevation change matrix visualization for a park.

    Returns a PNG heatmap showing elevation changes between trail points,
    useful for understanding trail difficulty and elevation profiles.

    **Example usage:**
    - Yosemite matrix: `/parks/yose/viz/elevation-matrix`
    - Grand Canyon matrix: `/parks/grca/viz/elevation-matrix`

    **Use cases:**
    - Analyze trail difficulty patterns
    - Visualize elevation gain/loss across trails
    - Compare elevation profiles between different trail segments
    """
    # Construct file path
    viz_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "profiling_results",
        "visualizations",
        "elevation_changes",
    )
    file_path = os.path.join(viz_dir, f"{park_code}_elevation_matrix.png")

    # Check if file exists
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404,
            detail=f"Elevation matrix not found for park code '{park_code}'. The park may not exist or visualization has not been generated.",
        )

    # Return PNG file (inline display, not download)
    return FileResponse(
        file_path,
        media_type="image/png",
    )


@app.get(
    "/parks/{park_code}/trails/{trail_slug}/viz/3d",
    tags=["Visualizations"],
    summary="Get 3D trail visualization",
    description="""
    Returns an interactive 3D visualization of a trail with elevation data.

    The visualization displays the trail's elevation profile in an interactive 3D space
    that can be rotated, zoomed, and panned. Requires elevation data to be available.
    """,
    responses={
        200: {
            "content": {"text/html": {}},
            "description": "Interactive HTML 3D visualization",
        },
        404: {"description": "Trail not found or elevation data not available"},
    },
)
async def get_trail_3d_visualization(
    park_code: str = Path(
        ...,
        description="4-character lowercase park code (e.g., 'yose' for Yosemite)",
        min_length=4,
        max_length=4,
        pattern="^[a-z]{4}$",
        examples=["yose", "grca", "zion"],
    ),
    trail_slug: str = Path(
        ...,
        description="URL-safe trail slug (e.g., 'half_dome_trail')",
        min_length=1,
        max_length=255,
        pattern="^[a-z0-9_-]+$",
        examples=["half_dome_trail", "bright_angel_trail"],
    ),
    z_scale: float = Query(
        default=5.0,
        description="Z-axis exaggeration factor for visualization (default: 5.0)",
        ge=1.0,
        le=20.0,
    ),
):
    """
    Get interactive 3D visualization for a specific trail.

    Returns an HTML page with an interactive Plotly 3D visualization showing:
    - Trail path with elevation profile
    - Terrain-based color gradient (elevation changes)
    - Interactive rotation, zoom, and pan controls
    - Trail statistics (distance, elevation gain/loss, etc.)

    **Example usage:**
    - Half Dome trail: `/parks/yose/trails/half_dome_trail/viz/3d`
    - With custom z-scale: `/parks/yose/trails/half_dome_trail/viz/3d?z_scale=10`

    **Use cases:**
    - Explore trail elevation profiles interactively
    - Visualize trail difficulty and terrain
    - Embed 3D trail views in web applications

    **Note:** Requires elevation data to be collected for the trail.
    """
    try:
        # Query database to verify trail exists and get trail_name
        engine = get_db_engine()
        query = """
            SELECT trail_name
            FROM usgs_trail_elevations
            WHERE park_code = :park_code
            AND trail_slug = :trail_slug
            AND collection_status IN ('COMPLETE', 'PARTIAL')
            LIMIT 1
        """

        with engine.connect() as conn:
            result = conn.execute(
                text(query), {"park_code": park_code, "trail_slug": trail_slug}
            )
            row = result.fetchone()

        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"Trail '{trail_slug}' not found for park '{park_code}' or elevation data not available",
            )

        trail_name = row.trail_name

        # Construct HTML file path
        viz_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "profiling_results",
            "visualizations",
            "3d_trails",
        )
        file_path = os.path.join(viz_dir, f"{park_code}_{trail_slug}_3d.html")

        # Check if visualization already exists
        if not os.path.exists(file_path):
            # Import and instantiate Trail3DVisualizer
            # Import here to avoid circular imports and unnecessary loading
            sys.path.append(os.path.dirname(os.path.dirname(__file__)))
            from profiling.modules.trail_3d_viz import Trail3DVisualizer

            # Generate visualization on-demand
            visualizer = Trail3DVisualizer()
            result_path = visualizer.create_3d_visualization(
                park_code=park_code, trail_name=trail_name, z_exaggeration=z_scale
            )

            if not result_path or not os.path.exists(result_path):
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to generate 3D visualization for trail '{trail_slug}'",
                )

            file_path = result_path

        # Return HTML file (inline display)
        return FileResponse(
            file_path,
            media_type="text/html",
        )

    except HTTPException:
        # Re-raise HTTP exceptions (like 404)
        raise
    except Exception as e:
        # Catch any other errors and return 500
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving 3D visualization: {str(e)}",
        )


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint to verify API and database connectivity.

    Returns the status of the API server and database connection.
    Useful for monitoring and load balancer health checks.
    """
    try:
        # Test database connection
        engine = get_db_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        return {
            "status": "healthy",
            "database": "connected",
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
        }

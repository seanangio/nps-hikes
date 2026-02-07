"""
NPS Trails API

A FastAPI application that provides access to National Park trail data
collected from OpenStreetMap and The National Map.

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
from sqlalchemy import text

# Add parent directory to path to import project modules
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from api.database import get_db_engine
from api.models import AllTrailsResponse, Park, ParksResponse, ParkTrailsResponse
from api.queries import fetch_all_parks, fetch_all_trails, fetch_trails_for_park

# Create FastAPI app with metadata for OpenAPI documentation
app = FastAPI(
    title="NPS Trails API",
    description="""
    API for exploring National Park hiking trails from OpenStreetMap and The National Map data sources.

    ## Features

    * List all National Parks visited with metadata and coordinates
    * Query all trails across all parks or by specific park
    * Filter trails by length range, state, or data source
    * Filter by hiking status (trails hiked vs not hiked)
    * Automatic deduplication (TNM preferred over OSM for duplicates)
    * Get trail statistics and metadata

    ## Data Sources

    This API provides access to trail data collected from:
    - **OpenStreetMap (OSM)**: Community-contributed trail data
    - **The National Map (TNM)**: USGS trail datasets

    ## Example Park Codes

    - `yose` - Yosemite National Park
    - `grca` - Grand Canyon National Park
    - `zion` - Zion National Park
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
            "all_trails": "/trails",
            "trails_by_park": "/parks/{park_code}/trails",
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
    Returns all National Parks visited with metadata.

    By default, excludes park descriptions.
    Use `include_description=true` to include full park descriptions.
    """,
)
async def get_all_parks(
    include_description: bool = Query(
        default=False,
        description="Include full park descriptions in the response (increases response size)",
    ),
):
    """
    Get all parks with metadata.

    Returns a list of all National Parks visited, including:
    - Park codes (used in other endpoints)
    - Park names and locations
    - Coordinates (latitude/longitude)
    - Visit dates (month/year)
    - NPS website URLs
    - Descriptions (optional, excluded by default)

    **Example queries:**
    - All parks (without descriptions): `/parks`
    - All parks (with descriptions): `/parks?include_description=true`

    **Use cases:**
    - Get park codes for use in other endpoints (trails, visualizations)
    - Build a map of visited parks using coordinates
    - Display a list of parks with visit dates
    """
    try:
        # Fetch parks from database
        result = fetch_all_parks(include_description=include_description)
        return result

    except Exception as e:
        # Catch any errors and return 500
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving parks: {str(e)}",
        )


@app.get(
    "/parks/{park_code}/trails",
    response_model=ParkTrailsResponse,
    tags=["Trails"],
    summary="Get all trails for a park",
    description="""
    Returns all hiking trails from OpenStreetMap for the specified park.

    Supports filtering by trail length range and trail type.
    Results are ordered by trail length (longest first).
    """,
)
async def get_park_trails(
    park_code: str = Path(
        ...,
        description="4-character lowercase park code (e.g., 'yose' for Yosemite)",
        min_length=4,
        max_length=4,
        pattern="^[a-z]{4}$",
        examples=["yose", "grca", "zion"],
    ),
    min_length: float | None = Query(
        default=None,
        description="Minimum trail length in miles (e.g., 3.0)",
        ge=0,
        le=100,
    ),
    max_length: float | None = Query(
        default=None,
        description="Maximum trail length in miles (e.g., 5.0)",
        ge=0,
        le=100,
    ),
    trail_type: str | None = Query(
        default=None,
        description="Filter by OSM highway type (e.g., 'path', 'footway', 'track')",
    ),
):
    """
    Get all trails for a specific park.

    Returns trail data including names, lengths, types, and summary statistics.
    Supports filtering by length range and trail type.

    **Common park codes:**
    - `yose`: Yosemite National Park
    - `grca`: Grand Canyon National Park
    - `zion`: Zion National Park
    - `yell`: Yellowstone National Park
    - `romo`: Rocky Mountain National Park

    **Common trail types:**
    - `path`: General hiking paths
    - `footway`: Pedestrian footways
    - `track`: Unpaved tracks
    - `steps`: Stairs/steps

    **Example queries:**
    - All trails: `/parks/yose/trails`
    - Trails 3-5 miles: `/parks/yose/trails?min_length=3&max_length=5`
    - Only paths: `/parks/yose/trails?trail_type=path`
    """
    try:
        # Fetch trails from database
        result = fetch_trails_for_park(
            park_code=park_code,
            min_length=min_length,
            max_length=max_length,
            trail_type=trail_type,
        )

        # Return 404 if no trails found
        if result["trail_count"] == 0:
            raise HTTPException(
                status_code=404,
                detail=f"No trails found for park code '{park_code}'. Park may not exist or has no trail data.",
            )

        return result

    except HTTPException:
        # Re-raise HTTP exceptions (like 404)
        raise
    except Exception as e:
        # Catch any other errors and return 500
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving trails: {str(e)}",
        )


@app.get(
    "/trails",
    response_model=AllTrailsResponse,
    tags=["Trails"],
    summary="Get all trails across all parks",
    description="""
    Returns all hiking trails from both TNM and OSM data sources across all parks.

    Combines TNM and OSM data, preferring TNM when duplicates exist (based on fuzzy name matching).
    Supports filtering by length, park, state, source, and hiking status.
    """,
)
async def get_all_trails(
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
):
    """
    Get all trails across all parks with optional filters.

    This endpoint combines trail data from The National Map (TNM) and OpenStreetMap (OSM),
    automatically deduplicating trails that appear in both sources (TNM is preferred).

    **Deduplication Logic:**
    - Trails with similar names (>70% similarity) in the same park are deduplicated
    - TNM trails are preferred over OSM when duplicates are detected
    - Each trail is marked with its source ('TNM' or 'OSM')

    **Example queries:**
    - All trails: `/trails`
    - Trails I've hiked: `/trails?hiked=true`
    - Long trails (>10 miles): `/trails?min_length=10`
    - California trails: `/trails?state=CA`
    - Yosemite trails from TNM: `/trails?park_code=yose&source=TNM`
    - Trails I haven't hiked yet in Utah: `/trails?state=UT&hiked=false`
    """
    try:
        # Fetch trails from database
        result = fetch_all_trails(
            min_length=min_length,
            max_length=max_length,
            park_code=park_code,
            state=state,
            source=source,
            hiked=hiked,
        )

        return result

    except Exception as e:
        # Catch any errors and return 500
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving trails: {str(e)}",
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

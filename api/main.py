"""
NPS Trails API

A FastAPI application that provides access to National Park trail data
collected from OpenStreetMap and The National Map.

This API exposes analytical outputs from the NPS Hikes project, allowing
users to query trail information without needing to run the collection pipeline.
"""

import os
import sys

from fastapi import FastAPI, HTTPException, Path, Query
from sqlalchemy import text

# Add parent directory to path to import project modules
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from api.database import get_db_engine
from api.models import ParkTrailsResponse
from api.queries import fetch_trails_for_park

# Create FastAPI app with metadata for OpenAPI documentation
app = FastAPI(
    title="NPS Trails API",
    description="""
    API for exploring National Park hiking trails from OpenStreetMap and The National Map data sources.

    ## Features

    * Query trails by park code
    * Filter trails by length range
    * Filter trails by type (path, footway, track, etc.)
    * Get trail statistics and metadata

    ## Data Sources

    This API provides access to trail data collected from:
    - **OpenStreetMap (OSM)**: Community-contributed trail data
    - **The National Map (TNM)**: USGS trail datasets (coming soon)

    ## Example Park Codes

    - `yose` - Yosemite National Park
    - `grca` - Grand Canyon National Park
    - `zion` - Zion National Park
    - `yell` - Yellowstone National Park
    - `romo` - Rocky Mountain National Park
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
            "trails_by_park": "/parks/{park_code}/trails",
            "health_check": "/health",
        },
    }


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

"""
Pydantic models for API request/response validation.

These models define the structure of API responses and automatically
generate OpenAPI schema definitions.
"""

from typing import Any

from pydantic import BaseModel, Field


class PaginationMetadata(BaseModel):
    """
    Pagination metadata for paginated API responses.

    Provides information about the current page, total results,
    and navigation flags for next/previous pages.
    """

    limit: int = Field(
        ...,
        description="Number of items per page",
        ge=1,
        le=1000,
        examples=[50],
    )
    offset: int = Field(
        ...,
        description="Number of items skipped (starting position)",
        ge=0,
        examples=[0],
    )
    total_count: int = Field(
        ...,
        description="Total number of items matching the query",
        ge=0,
        examples=[347],
    )
    has_next: bool = Field(
        ...,
        description="Whether there are more pages after this one",
        examples=[True],
    )
    has_prev: bool = Field(
        ...,
        description="Whether there are previous pages before this one",
        examples=[False],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "limit": 50,
                    "offset": 0,
                    "total_count": 347,
                    "has_next": True,
                    "has_prev": False,
                }
            ]
        }
    }


class Trail(BaseModel):
    """
    Individual trail information.

    Represents a single hiking trail with metadata but no geometry.
    Combines data from both TNM and OSM sources.
    """

    trail_id: str = Field(
        ...,
        description="Unique trail identifier (permanent_identifier for TNM, osm_id for OSM)",
        examples=["550779"],
    )
    trail_name: str | None = Field(
        None,
        description="Trail name (may be null for unnamed trails)",
        examples=["Mono Pass Trail"],
    )
    park_code: str = Field(
        ...,
        description="4-character lowercase park code",
        pattern="^[a-z]{4}$",
        examples=["yose"],
    )
    park_name: str | None = Field(
        None,
        description="Short park name",
        examples=["Yosemite"],
    )
    states: str | None = Field(
        None,
        description="States where parent park is located (approximate - trail may not span all states)",
        examples=["CA"],
    )
    source: str = Field(
        ...,
        description="Data source (TNM or OSM)",
        examples=["TNM"],
    )
    length_miles: float = Field(
        ...,
        description="Trail length in miles",
        ge=0,
        examples=[8.2],
    )
    geometry_type: str = Field(
        ...,
        description="Geometry type (LineString or MultiLineString)",
        examples=["LineString"],
    )
    highway_type: str | None = Field(
        None,
        description="OSM highway tag (path, footway, track, etc.) - only available for OSM trails",
        examples=["path"],
    )
    hiked: bool = Field(
        ...,
        description="Whether this trail has been hiked",
        examples=[True],
    )
    viz_3d_available: bool = Field(
        ...,
        description="Whether 3D visualization is available for this trail (requires elevation data)",
        examples=[True],
    )
    viz_3d_slug: str | None = Field(
        None,
        description="URL-safe trail slug for 3D visualization endpoint (only present if viz_3d_available is true)",
        examples=["mono_pass_trail"],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "trail_id": "550779",
                    "trail_name": "Mono Pass Trail",
                    "park_code": "yose",
                    "park_name": "Yosemite",
                    "states": "CA",
                    "source": "TNM",
                    "length_miles": 8.2,
                    "geometry_type": "LineString",
                    "highway_type": None,
                    "hiked": True,
                    "viz_3d_available": True,
                    "viz_3d_slug": "mono_pass_trail",
                }
            ]
        }
    }


class TrailsResponse(BaseModel):
    """
    Response model for all trails endpoint.

    Contains summary statistics, a list of trails, and pagination metadata.
    """

    trail_count: int = Field(
        ...,
        description="Number of trails returned in this page",
        ge=0,
        examples=[50],
    )
    total_miles: float = Field(
        ...,
        description="Total trail mileage for trails in this page",
        ge=0,
        examples=[342.7],
    )
    trails: list[Trail] = Field(
        ...,
        description="List of trails matching the query",
    )
    pagination: PaginationMetadata = Field(
        ...,
        description="Pagination metadata including total count and navigation flags",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "trail_count": 2,
                    "total_miles": 20.5,
                    "pagination": {
                        "limit": 50,
                        "offset": 0,
                        "total_count": 127,
                        "has_next": True,
                        "has_prev": False,
                    },
                    "trails": [
                        {
                            "trail_id": "550779",
                            "trail_name": "Half Dome Trail",
                            "park_code": "yose",
                            "park_name": "Yosemite",
                            "states": "CA",
                            "source": "TNM",
                            "length_miles": 14.2,
                            "geometry_type": "LineString",
                            "highway_type": None,
                            "hiked": True,
                            "viz_3d_available": True,
                            "viz_3d_slug": "mariposa_grove_trail",
                        },
                        {
                            "trail_id": "123456789",
                            "trail_name": "Mist Trail",
                            "park_code": "yose",
                            "park_name": "Yosemite",
                            "states": "CA",
                            "source": "OSM",
                            "length_miles": 6.3,
                            "geometry_type": "LineString",
                            "highway_type": "path",
                            "hiked": False,
                            "viz_3d_available": False,
                            "viz_3d_slug": None,
                        },
                    ],
                }
            ]
        }
    }


class Park(BaseModel):
    """
    Individual park information.

    Represents a single National Park with metadata.
    """

    park_code: str = Field(
        ...,
        description="4-character lowercase park code",
        pattern="^[a-z]{4}$",
        examples=["yose"],
    )
    park_name: str | None = Field(
        None,
        description="Short park name",
        examples=["Yosemite"],
    )
    full_name: str | None = Field(
        None,
        description="Official full name of the park",
        examples=["Yosemite National Park"],
    )
    states: str | None = Field(
        None,
        description="States where the park is located",
        examples=["CA"],
    )
    latitude: float | None = Field(
        None,
        description="Latitude coordinate",
        ge=-90,
        le=90,
        examples=[37.8651],
    )
    longitude: float | None = Field(
        None,
        description="Longitude coordinate",
        ge=-180,
        le=180,
        examples=[-119.5383],
    )
    url: str | None = Field(
        None,
        description="NPS website URL for the park",
        examples=["https://www.nps.gov/yose/index.htm"],
    )
    designation: str | None = Field(
        None,
        description="NPS designation (e.g., 'National Park', 'National Park & Preserve')",
        examples=["National Park"],
    )
    visit_month: str | None = Field(
        None,
        description="Month of park visit",
        examples=["July"],
    )
    visit_year: int | None = Field(
        None,
        description="Year of park visit",
        examples=[2023],
    )
    description: str | None = Field(
        None,
        description="Park description (only included when include_description=true)",
        examples=[
            "Not just a great valley, but a shrine to human foresight, the strength of granite..."
        ],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "park_code": "yose",
                    "park_name": "Yosemite",
                    "full_name": "Yosemite National Park",
                    "states": "CA",
                    "latitude": 37.8651,
                    "longitude": -119.5383,
                    "url": "https://www.nps.gov/yose/index.htm",
                    "visit_month": "July",
                    "visit_year": 2023,
                }
            ]
        },
    }


class ParksResponse(BaseModel):
    """
    Response model for parks listing endpoint.

    Contains park count, visited count, and a list of all National Parks.
    """

    park_count: int = Field(
        ...,
        description="Total number of parks returned",
        ge=0,
        examples=[63],
    )
    visited_count: int = Field(
        ...,
        description="Number of parks that have been visited",
        ge=0,
        examples=[36],
    )
    parks: list[Park] = Field(
        ...,
        description="List of parks",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "park_count": 2,
                    "visited_count": 1,
                    "parks": [
                        {
                            "park_code": "dena",
                            "park_name": "Denali",
                            "full_name": "Denali National Park & Preserve",
                            "designation": "National Park & Preserve",
                            "states": "AK",
                            "latitude": 63.3334,
                            "longitude": -150.5013,
                            "url": "https://www.nps.gov/dena/index.htm",
                        },
                        {
                            "park_code": "yose",
                            "park_name": "Yosemite",
                            "full_name": "Yosemite National Park",
                            "designation": "National Park",
                            "states": "CA",
                            "latitude": 37.8651,
                            "longitude": -119.5383,
                            "url": "https://www.nps.gov/yose/index.htm",
                            "visit_month": "July",
                            "visit_year": 2023,
                        },
                    ],
                }
            ]
        }
    }


class NlqRequest(BaseModel):
    """Request model for natural language trail/park queries."""

    query: str = Field(
        ...,
        description="Natural language question about trails or parks",
        min_length=3,
        max_length=500,
        examples=[
            "Show me long trails in Yosemite",
            "What parks have I visited?",
            "Find hikes under 3 miles in Utah",
        ],
    )


class NlqResponse(BaseModel):
    """Response model for natural language queries.

    Returns the original query, how it was interpreted, which function
    was called, and the results (same structure as /trails or /parks).
    """

    original_query: str = Field(
        ...,
        description="The original natural language query",
    )
    interpreted_as: dict[str, Any] = Field(
        ...,
        description="The structured parameters extracted from the query",
    )
    function_called: str = Field(
        ...,
        description="Which function was called (search_trails or search_parks)",
    )
    results: dict[str, Any] = Field(
        ...,
        description="The API results (same structure as /trails or /parks response)",
    )

"""
Pydantic models for API request/response validation.

These models define the structure of API responses and automatically
generate OpenAPI schema definitions.
"""

from pydantic import BaseModel, Field


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
        description="Full park name",
        examples=["Yosemite National Park"],
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
                    "park_name": "Yosemite National Park",
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

    Contains summary statistics and a list of trails across all parks.
    """

    trail_count: int = Field(
        ...,
        description="Number of trails returned",
        ge=0,
        examples=[127],
    )
    total_miles: float = Field(
        ...,
        description="Total trail mileage for all returned trails",
        ge=0,
        examples=[892.3],
    )
    trails: list[Trail] = Field(
        ...,
        description="List of trails matching the query",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "trail_count": 2,
                    "total_miles": 20.5,
                    "trails": [
                        {
                            "trail_id": "550779",
                            "trail_name": "Half Dome Trail",
                            "park_code": "yose",
                            "park_name": "Yosemite National Park",
                            "states": "CA",
                            "source": "TNM",
                            "length_miles": 14.2,
                            "geometry_type": "LineString",
                            "highway_type": None,
                            "hiked": True,
                            "viz_3d_available": True,
                            "viz_3d_slug": "half_dome_trail",
                        },
                        {
                            "trail_id": "123456789",
                            "trail_name": "Mist Trail",
                            "park_code": "yose",
                            "park_name": "Yosemite National Park",
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
        description="Full park name",
        examples=["Yosemite National Park"],
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
                    "park_name": "Yosemite National Park",
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
                            "park_name": "Denali National Park & Preserve",
                            "full_name": "Denali National Park & Preserve",
                            "designation": "National Park & Preserve",
                            "states": "AK",
                            "latitude": 63.3334,
                            "longitude": -150.5013,
                            "url": "https://www.nps.gov/dena/index.htm",
                        },
                        {
                            "park_code": "yose",
                            "park_name": "Yosemite National Park",
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

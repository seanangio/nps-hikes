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
    """

    osm_id: int = Field(
        ...,
        description="OpenStreetMap feature ID",
        examples=[123456789],
    )
    name: str | None = Field(
        None,
        description="Trail name (may be null for unnamed trails)",
        examples=["Mono Pass Trail"],
    )
    length_miles: float = Field(
        ...,
        description="Trail length in miles",
        ge=0,
        examples=[8.2],
    )
    highway_type: str = Field(
        ...,
        description="OSM highway tag (path, footway, track, etc.)",
        examples=["path"],
    )
    source: str = Field(
        ...,
        description="Data source (osm or tnm)",
        examples=["osm"],
    )
    geometry_type: str = Field(
        ...,
        description="Geometry type (LineString or MultiLineString)",
        examples=["LineString"],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "osm_id": 123456789,
                    "name": "Mono Pass Trail",
                    "length_miles": 8.2,
                    "highway_type": "path",
                    "source": "osm",
                    "geometry_type": "LineString",
                }
            ]
        }
    }


class ParkTrailsResponse(BaseModel):
    """
    Response model for park trails endpoint.

    Contains park information and a list of trails with summary statistics.
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
    trail_count: int = Field(
        ...,
        description="Number of trails returned",
        ge=0,
        examples=[47],
    )
    total_miles: float = Field(
        ...,
        description="Total trail mileage for all returned trails",
        ge=0,
        examples=[234.5],
    )
    trails: list[Trail] = Field(
        ...,
        description="List of trails in the park",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "park_code": "yose",
                    "park_name": "Yosemite National Park",
                    "trail_count": 2,
                    "total_miles": 15.8,
                    "trails": [
                        {
                            "osm_id": 123456789,
                            "name": "Mono Pass Trail",
                            "length_miles": 8.2,
                            "highway_type": "path",
                            "source": "osm",
                            "geometry_type": "LineString",
                        },
                        {
                            "osm_id": 987654321,
                            "name": "Cathedral Lakes Trail",
                            "length_miles": 7.6,
                            "highway_type": "path",
                            "source": "osm",
                            "geometry_type": "LineString",
                        },
                    ],
                }
            ]
        }
    }


class AllTrail(BaseModel):
    """
    Trail information for the all-trails endpoint.

    Includes trail metadata from both TNM and OSM sources, along with
    park information and hiking status.
    """

    trail_id: str = Field(
        ...,
        description="Unique trail identifier (permanent_identifier for TNM, osm_id for OSM)",
        examples=["550779"],
    )
    trail_name: str = Field(
        ...,
        description="Trail name",
        examples=["Half Dome Trail"],
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
        examples=[14.2],
    )
    geometry_type: str = Field(
        ...,
        description="Geometry type (LineString, MultiLineString, etc.)",
        examples=["LineString"],
    )
    hiked: bool = Field(
        ...,
        description="Whether this trail has been hiked",
        examples=[True],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "trail_id": "550779",
                    "trail_name": "Half Dome Trail",
                    "park_code": "yose",
                    "park_name": "Yosemite National Park",
                    "states": "CA",
                    "source": "TNM",
                    "length_miles": 14.2,
                    "geometry_type": "LineString",
                    "hiked": True,
                }
            ]
        }
    }


class AllTrailsResponse(BaseModel):
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
    trails: list[AllTrail] = Field(
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
                            "hiked": True,
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
                            "hiked": False,
                        },
                    ],
                }
            ]
        }
    }

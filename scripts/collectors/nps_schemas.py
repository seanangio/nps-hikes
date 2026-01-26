"""Pydantic schemas for validating NPS API responses."""

from pydantic import BaseModel, Field, field_validator, model_validator


class NPSParkResponse(BaseModel):
    """Schema for validating NPS parks API response data.

    Validates the structure and content of park data returned from the
    NPS API /parks endpoint. Ensures required fields are present and
    coordinate data is valid before it enters the processing pipeline.
    """

    parkCode: str = Field(
        ..., min_length=4, max_length=4, description="NPS park code (4 characters)"
    )
    fullName: str = Field(..., min_length=1, description="Full park name")
    name: str = Field(default="", description="Short park name")
    states: str = Field(default="", description="State codes (comma-separated)")
    url: str = Field(default="", description="Park website URL")
    description: str = Field(default="", description="Park description")
    latitude: str | None = Field(default=None, description="Latitude as string")
    longitude: str | None = Field(default=None, description="Longitude as string")

    @field_validator("latitude", "longitude")
    @classmethod
    def validate_coordinate_strings(cls, v: str | None) -> str | None:
        """Ensure coordinate values can be converted to float if present.

        Args:
            v: The coordinate value from the API (or None)

        Returns:
            The validated coordinate string, or None

        Raises:
            ValueError: If the coordinate string cannot be converted to float
        """
        if v is None or v == "":
            return None
        try:
            float(v)
            return v
        except ValueError:
            raise ValueError(f"Coordinate value '{v}' cannot be converted to float")

    @model_validator(mode="after")
    def validate_coordinate_ranges(self):
        """Validate that coordinates are within valid geographic ranges.

        Checks that latitude is in [-90, 90] and longitude is in [-180, 180].
        This validation runs after individual field validators pass.

        Returns:
            self: The validated model instance

        Raises:
            ValueError: If coordinates are outside valid geographic ranges
        """
        lat = self.latitude
        lon = self.longitude

        # If both are None, that's acceptable (some parks may not have coordinates)
        if lat is None and lon is None:
            return self

        # Validate latitude range if present
        if lat is not None:
            lat_float = float(lat)
            if not (-90 <= lat_float <= 90):
                raise ValueError(f"Latitude {lat_float} out of valid range [-90, 90]")

        # Validate longitude range if present
        if lon is not None:
            lon_float = float(lon)
            if not (-180 <= lon_float <= 180):
                raise ValueError(
                    f"Longitude {lon_float} out of valid range [-180, 180]"
                )

        return self


class NPSBoundaryGeometry(BaseModel):
    """Schema for validating GeoJSON geometry objects.

    Validates the geometry structure returned by the NPS boundaries API.
    GeoJSON geometries have a type (Polygon, MultiPolygon, etc.) and
    coordinates array.
    """

    type: str = Field(..., description="Geometry type (e.g., Polygon, MultiPolygon)")
    coordinates: list = Field(..., description="Nested coordinate arrays")

    @field_validator("type")
    @classmethod
    def validate_geometry_type(cls, v: str) -> str:
        """Ensure geometry type is one of the valid GeoJSON types."""
        valid_types = {
            "Point",
            "MultiPoint",
            "LineString",
            "MultiLineString",
            "Polygon",
            "MultiPolygon",
            "GeometryCollection",
        }
        if v not in valid_types:
            raise ValueError(
                f"Invalid geometry type '{v}'. Must be one of: {valid_types}"
            )
        return v


class NPSBoundaryFeature(BaseModel):
    """Schema for validating GeoJSON Feature objects.

    A Feature wraps a geometry object and can include properties.
    This is the standard GeoJSON Feature structure.
    """

    type: str = Field(..., description="Must be 'Feature'")
    geometry: NPSBoundaryGeometry = Field(..., description="The geometry object")
    properties: dict = Field(default_factory=dict, description="Feature properties")

    @field_validator("type")
    @classmethod
    def validate_feature_type(cls, v: str) -> str:
        """Ensure type is 'Feature'."""
        if v != "Feature":
            raise ValueError(f"Feature type must be 'Feature', got '{v}'")
        return v


class NPSBoundaryResponse(BaseModel):
    """Schema for validating NPS boundaries API response.

    The NPS boundaries API can return data in multiple formats:
    1. FeatureCollection with multiple features
    2. Single Feature object
    3. Direct geometry object

    This schema validates the most common format (FeatureCollection).
    For single Features or direct geometries, the code handles them
    separately in the collector logic.
    """

    type: str = Field(..., description="GeoJSON type")
    features: list[NPSBoundaryFeature] | None = Field(
        default=None, description="Array of Feature objects (for FeatureCollection)"
    )
    geometry: NPSBoundaryGeometry | None = Field(
        default=None, description="Direct geometry (for single Feature)"
    )

    @field_validator("type")
    @classmethod
    def validate_geojson_type(cls, v: str) -> str:
        """Ensure type is a valid GeoJSON type."""
        valid_types = {"FeatureCollection", "Feature"}
        if v not in valid_types:
            raise ValueError(
                f"Top-level type must be 'FeatureCollection' or 'Feature', got '{v}'"
            )
        return v

    @model_validator(mode="after")
    def validate_structure(self):
        """Ensure the response has the appropriate fields for its type."""
        if self.type == "FeatureCollection":
            if self.features is None:
                raise ValueError("FeatureCollection must have 'features' array")
        elif self.type == "Feature":
            if self.geometry is None:
                raise ValueError("Feature must have 'geometry' object")
        return self

"""
Unit tests for NPS Pydantic validation schemas.

Tests the Pydantic schemas used to validate NPS API responses,
including park data and boundary GeoJSON data.
"""

import pytest
from pydantic import ValidationError

from scripts.collectors.nps_schemas import (
    NPSBoundaryFeature,
    NPSBoundaryGeometry,
    NPSBoundaryResponse,
    NPSParkResponse,
)


class TestNPSParkResponse:
    """Test cases for NPSParkResponse schema validation."""

    def test_valid_park_data(self):
        """Test that valid park data passes validation."""
        valid_data = {
            "parkCode": "yell",
            "fullName": "Yellowstone National Park",
            "name": "Yellowstone",
            "states": "ID,MT,WY",
            "url": "https://www.nps.gov/yell/index.htm",
            "description": "Visit Yellowstone and experience the world's first national park.",
            "latitude": "44.59824417",
            "longitude": "-110.5471695",
        }

        park = NPSParkResponse(**valid_data)

        assert park.parkCode == "yell"
        assert park.fullName == "Yellowstone National Park"
        assert park.latitude == "44.59824417"
        assert park.longitude == "-110.5471695"

    def test_missing_required_field(self):
        """Test that missing required fields are caught."""
        invalid_data = {
            # Missing parkCode (required)
            "fullName": "Test Park",
            "latitude": "44.59824417",
            "longitude": "-110.5471695",
        }

        with pytest.raises(ValidationError) as exc_info:
            NPSParkResponse(**invalid_data)

        assert exc_info.value.error_count() == 1
        errors = exc_info.value.errors()
        assert errors[0]["loc"] == ("parkCode",)
        assert errors[0]["type"] == "missing"

    def test_invalid_coordinate_range_latitude(self):
        """Test that out-of-range latitude is caught."""
        invalid_data = {
            "parkCode": "test",
            "fullName": "Test Park",
            "latitude": "999.0",  # Invalid - outside [-90, 90]
            "longitude": "-110.0",
        }

        with pytest.raises(ValidationError) as exc_info:
            NPSParkResponse(**invalid_data)

        assert exc_info.value.error_count() == 1
        assert "out of valid range" in str(exc_info.value)

    def test_invalid_coordinate_range_longitude(self):
        """Test that out-of-range longitude is caught."""
        invalid_data = {
            "parkCode": "test",
            "fullName": "Test Park",
            "latitude": "44.0",
            "longitude": "-999.0",  # Invalid - outside [-180, 180]
        }

        with pytest.raises(ValidationError) as exc_info:
            NPSParkResponse(**invalid_data)

        assert exc_info.value.error_count() == 1
        assert "out of valid range" in str(exc_info.value)

    def test_invalid_coordinate_format(self):
        """Test that non-numeric coordinates are caught."""
        invalid_data = {
            "parkCode": "test",
            "fullName": "Test Park",
            "latitude": "not-a-number",
            "longitude": "-110.0",
        }

        with pytest.raises(ValidationError) as exc_info:
            NPSParkResponse(**invalid_data)

        assert exc_info.value.error_count() == 1
        assert "cannot be converted to float" in str(exc_info.value)

    def test_park_code_length_too_short(self):
        """Test that park codes shorter than 4 characters are rejected."""
        invalid_data = {"parkCode": "abc", "fullName": "Test Park"}

        with pytest.raises(ValidationError) as exc_info:
            NPSParkResponse(**invalid_data)

        assert exc_info.value.error_count() == 1
        errors = exc_info.value.errors()
        assert errors[0]["loc"] == ("parkCode",)
        assert "at least 4 characters" in errors[0]["msg"]

    def test_park_code_length_too_long(self):
        """Test that park codes longer than 4 characters are rejected."""
        invalid_data = {"parkCode": "abcde", "fullName": "Test Park"}

        with pytest.raises(ValidationError) as exc_info:
            NPSParkResponse(**invalid_data)

        assert exc_info.value.error_count() == 1
        errors = exc_info.value.errors()
        assert errors[0]["loc"] == ("parkCode",)
        assert "at most 4 characters" in errors[0]["msg"]

    def test_valid_park_code_length(self):
        """Test that 4-character park codes are accepted."""
        valid_data = {"parkCode": "yell", "fullName": "Yellowstone National Park"}

        park = NPSParkResponse(**valid_data)

        assert park.parkCode == "yell"
        assert len(park.parkCode) == 4

    def test_optional_fields_with_defaults(self):
        """Test that optional fields default correctly."""
        minimal_data = {"parkCode": "test", "fullName": "Test Park"}

        park = NPSParkResponse(**minimal_data)

        assert park.parkCode == "test"
        assert park.fullName == "Test Park"
        assert park.name == ""
        assert park.states == ""
        assert park.url == ""
        assert park.description == ""
        assert park.latitude is None
        assert park.longitude is None

    def test_none_coordinates_accepted(self):
        """Test that parks without coordinates are accepted."""
        data = {
            "parkCode": "test",
            "fullName": "Test Park",
            "latitude": None,
            "longitude": None,
        }

        park = NPSParkResponse(**data)

        assert park.latitude is None
        assert park.longitude is None

    def test_empty_string_coordinates_converted_to_none(self):
        """Test that empty string coordinates are converted to None."""
        data = {
            "parkCode": "test",
            "fullName": "Test Park",
            "latitude": "",
            "longitude": "",
        }

        park = NPSParkResponse(**data)

        assert park.latitude is None
        assert park.longitude is None

    def test_extra_fields_ignored(self):
        """Test that extra fields in API response are ignored."""
        data_with_extra = {
            "parkCode": "test",
            "fullName": "Test Park",
            "extraField": "should be ignored",
            "anotherExtra": 123,
        }

        park = NPSParkResponse(**data_with_extra)

        assert park.parkCode == "test"
        assert park.fullName == "Test Park"
        assert not hasattr(park, "extraField")


class TestNPSBoundaryGeometry:
    """Test cases for NPSBoundaryGeometry schema validation."""

    def test_valid_polygon_geometry(self):
        """Test that valid Polygon geometry passes validation."""
        valid_geometry = {
            "type": "Polygon",
            "coordinates": [
                [
                    [-110.0, 44.0],
                    [-110.0, 45.0],
                    [-109.0, 45.0],
                    [-109.0, 44.0],
                    [-110.0, 44.0],
                ]
            ],
        }

        geometry = NPSBoundaryGeometry(**valid_geometry)

        assert geometry.type == "Polygon"
        assert len(geometry.coordinates) == 1

    def test_valid_multipolygon_geometry(self):
        """Test that valid MultiPolygon geometry passes validation."""
        valid_geometry = {
            "type": "MultiPolygon",
            "coordinates": [
                [
                    [
                        [-110.0, 44.0],
                        [-110.0, 45.0],
                        [-109.0, 45.0],
                        [-109.0, 44.0],
                        [-110.0, 44.0],
                    ]
                ]
            ],
        }

        geometry = NPSBoundaryGeometry(**valid_geometry)

        assert geometry.type == "MultiPolygon"

    def test_invalid_geometry_type(self):
        """Test that invalid geometry types are rejected."""
        invalid_geometry = {
            "type": "InvalidType",
            "coordinates": [[[-110.0, 44.0]]],
        }

        with pytest.raises(ValidationError) as exc_info:
            NPSBoundaryGeometry(**invalid_geometry)

        assert exc_info.value.error_count() == 1
        assert "Invalid geometry type" in str(exc_info.value)

    def test_all_valid_geometry_types(self):
        """Test that all valid GeoJSON geometry types are accepted."""
        valid_types = [
            "Point",
            "MultiPoint",
            "LineString",
            "MultiLineString",
            "Polygon",
            "MultiPolygon",
            "GeometryCollection",
        ]

        for geom_type in valid_types:
            geometry = NPSBoundaryGeometry(type=geom_type, coordinates=[])
            assert geometry.type == geom_type


class TestNPSBoundaryFeature:
    """Test cases for NPSBoundaryFeature schema validation."""

    def test_valid_feature(self):
        """Test that valid Feature passes validation."""
        valid_feature = {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[[-110.0, 44.0]]]},
            "properties": {"name": "Test Park"},
        }

        feature = NPSBoundaryFeature(**valid_feature)

        assert feature.type == "Feature"
        assert feature.geometry.type == "Polygon"
        assert feature.properties == {"name": "Test Park"}

    def test_feature_without_properties(self):
        """Test that Feature without properties defaults to empty dict."""
        valid_feature = {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[[-110.0, 44.0]]]},
        }

        feature = NPSBoundaryFeature(**valid_feature)

        assert feature.properties == {}

    def test_invalid_feature_type(self):
        """Test that non-Feature type is rejected."""
        invalid_feature = {
            "type": "NotAFeature",
            "geometry": {"type": "Polygon", "coordinates": [[[-110.0, 44.0]]]},
            "properties": {},
        }

        with pytest.raises(ValidationError) as exc_info:
            NPSBoundaryFeature(**invalid_feature)

        assert exc_info.value.error_count() == 1
        assert "must be 'Feature'" in str(exc_info.value)

    def test_missing_geometry(self):
        """Test that Feature without geometry is rejected."""
        invalid_feature = {"type": "Feature", "properties": {}}

        with pytest.raises(ValidationError) as exc_info:
            NPSBoundaryFeature(**invalid_feature)

        assert exc_info.value.error_count() == 1
        errors = exc_info.value.errors()
        assert errors[0]["loc"] == ("geometry",)
        assert errors[0]["type"] == "missing"


class TestNPSBoundaryResponse:
    """Test cases for NPSBoundaryResponse schema validation."""

    def test_valid_feature_collection(self):
        """Test that valid FeatureCollection passes validation."""
        valid_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [-110.0, 44.0],
                                [-110.0, 45.0],
                                [-109.0, 45.0],
                                [-109.0, 44.0],
                                [-110.0, 44.0],
                            ]
                        ],
                    },
                    "properties": {"name": "Test Park"},
                }
            ],
        }

        boundary = NPSBoundaryResponse(**valid_data)

        assert boundary.type == "FeatureCollection"
        assert len(boundary.features) == 1
        assert boundary.features[0].geometry.type == "Polygon"

    def test_valid_single_feature(self):
        """Test that single Feature format passes validation."""
        valid_data = {
            "type": "Feature",
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [-110.0, 44.0],
                            [-110.0, 45.0],
                            [-109.0, 45.0],
                            [-109.0, 44.0],
                            [-110.0, 44.0],
                        ]
                    ]
                ],
            },
            "properties": {},
        }

        boundary = NPSBoundaryResponse(**valid_data)

        assert boundary.type == "Feature"
        assert boundary.geometry.type == "MultiPolygon"

    def test_empty_feature_collection(self):
        """Test that empty FeatureCollection passes schema validation."""
        # Note: Empty FeatureCollections are caught by collector logic, not schema
        data = {"type": "FeatureCollection", "features": []}

        boundary = NPSBoundaryResponse(**data)

        assert boundary.type == "FeatureCollection"
        assert boundary.features == []

    def test_feature_collection_without_features_array(self):
        """Test that FeatureCollection without features array is rejected."""
        invalid_data = {"type": "FeatureCollection"}

        with pytest.raises(ValidationError) as exc_info:
            NPSBoundaryResponse(**invalid_data)

        assert exc_info.value.error_count() == 1
        assert "must have 'features' array" in str(exc_info.value)

    def test_feature_without_geometry(self):
        """Test that Feature without geometry is rejected."""
        invalid_data = {"type": "Feature", "properties": {}}

        with pytest.raises(ValidationError) as exc_info:
            NPSBoundaryResponse(**invalid_data)

        assert exc_info.value.error_count() == 1
        assert "must have 'geometry' object" in str(exc_info.value)

    def test_invalid_top_level_type(self):
        """Test that invalid top-level type is rejected."""
        invalid_data = {"type": "Polygon", "coordinates": [[[-110.0, 44.0]]]}

        with pytest.raises(ValidationError) as exc_info:
            NPSBoundaryResponse(**invalid_data)

        assert exc_info.value.error_count() == 1
        error_msg = str(exc_info.value).lower()
        assert "featurecollection" in error_msg and "feature" in error_msg

    def test_feature_collection_with_multiple_features(self):
        """Test that FeatureCollection with multiple features works."""
        valid_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [[[-110.0, 44.0]]]},
                    "properties": {},
                },
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [[[-111.0, 45.0]]]},
                    "properties": {},
                },
            ],
        }

        boundary = NPSBoundaryResponse(**valid_data)

        assert boundary.type == "FeatureCollection"
        assert len(boundary.features) == 2

    def test_model_dump_returns_dict(self):
        """Test that model_dump() returns a dictionary for downstream processing."""
        valid_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [[[-110.0, 44.0]]]},
                    "properties": {},
                }
            ],
        }

        boundary = NPSBoundaryResponse(**valid_data)
        dumped = boundary.model_dump()

        assert isinstance(dumped, dict)
        assert dumped["type"] == "FeatureCollection"
        assert len(dumped["features"]) == 1

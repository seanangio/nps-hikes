"""
Unit tests for TNM (The National Map) validation schemas.

Tests cover both Pydantic schemas (API response validation) and
Pandera schemas (processed GeoDataFrame validation).
"""

import geopandas as gpd
import pandas as pd
import pytest
from pandera.errors import SchemaError, SchemaErrors
from pydantic import ValidationError
from shapely.geometry import LineString, MultiLineString, Point, Polygon

from config.settings import config
from scripts.collectors.tnm_schemas import (
    TNMFeature,
    TNMFeatureCollection,
    TNMFeatureProperties,
    TNMGeometry,
    TNMProcessedTrailsSchema,
)

# =============================================================================
# PYDANTIC SCHEMA TESTS - TNM API Response Validation
# =============================================================================


class TestTNMGeometry:
    """Test TNM geometry validation."""

    def test_valid_linestring_geometry(self):
        """Test valid LineString geometry passes validation."""
        geometry = {
            "type": "LineString",
            "coordinates": [[0, 0], [1, 1], [2, 2]],
        }
        result = TNMGeometry.model_validate(geometry)
        assert result.type == "LineString"
        assert len(result.coordinates) == 3

    def test_valid_multilinestring_geometry(self):
        """Test valid MultiLineString geometry passes validation."""
        geometry = {
            "type": "MultiLineString",
            "coordinates": [[[0, 0], [1, 1]], [[2, 2], [3, 3]]],
        }
        result = TNMGeometry.model_validate(geometry)
        assert result.type == "MultiLineString"

    def test_invalid_geometry_type(self):
        """Test invalid geometry type raises ValidationError."""
        geometry = {
            "type": "InvalidType",
            "coordinates": [[0, 0], [1, 1]],
        }
        with pytest.raises(ValidationError, match="Invalid geometry type"):
            TNMGeometry.model_validate(geometry)

    def test_missing_coordinates(self):
        """Test missing coordinates raises ValidationError."""
        geometry = {"type": "LineString"}
        with pytest.raises(ValidationError):
            TNMGeometry.model_validate(geometry)


class TestTNMFeatureProperties:
    """Test TNM feature properties validation."""

    def test_valid_properties_minimal(self):
        """Test valid properties with only required field."""
        props = {"permanentidentifier": "abc123"}
        result = TNMFeatureProperties.model_validate(props)
        assert result.permanentidentifier == "abc123"
        assert result.name is None
        assert result.lengthmiles is None

    def test_valid_properties_with_optionals(self):
        """Test valid properties with optional fields."""
        props = {
            "permanentidentifier": "abc123",
            "name": "Test Trail",
            "lengthmiles": 5.5,
        }
        result = TNMFeatureProperties.model_validate(props)
        assert result.permanentidentifier == "abc123"
        assert result.name == "Test Trail"
        assert result.lengthmiles == 5.5

    def test_empty_permanent_identifier(self):
        """Test empty permanent identifier raises ValidationError."""
        props = {"permanentidentifier": ""}
        with pytest.raises(ValidationError, match="at least 1 character"):
            TNMFeatureProperties.model_validate(props)

    def test_permanent_identifier_too_long(self):
        """Test permanent identifier over 100 chars raises ValidationError."""
        props = {"permanentidentifier": "a" * 101}
        with pytest.raises(ValidationError, match="at most 100 characters"):
            TNMFeatureProperties.model_validate(props)

    def test_missing_permanent_identifier(self):
        """Test missing permanent identifier raises ValidationError."""
        props = {"name": "Test Trail"}
        with pytest.raises(ValidationError):
            TNMFeatureProperties.model_validate(props)

    def test_extra_fields_allowed(self):
        """Test that extra fields from API are allowed."""
        props = {
            "permanentidentifier": "abc123",
            "extra_field": "extra_value",
            "another_field": 123,
        }
        result = TNMFeatureProperties.model_validate(props)
        assert result.permanentidentifier == "abc123"


class TestTNMFeature:
    """Test TNM feature validation."""

    def test_valid_feature(self):
        """Test valid GeoJSON feature passes validation."""
        feature = {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
            "properties": {"permanentidentifier": "abc123"},
        }
        result = TNMFeature.model_validate(feature)
        assert result.type == "Feature"
        assert result.geometry.type == "LineString"
        assert result.properties.permanentidentifier == "abc123"

    def test_invalid_feature_type(self):
        """Test feature with wrong type raises ValidationError."""
        feature = {
            "type": "InvalidFeature",
            "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
            "properties": {"permanentidentifier": "abc123"},
        }
        with pytest.raises(ValidationError):
            TNMFeature.model_validate(feature)


class TestTNMFeatureCollection:
    """Test TNM FeatureCollection validation."""

    def test_valid_feature_collection(self):
        """Test valid FeatureCollection passes validation."""
        collection = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
                    "properties": {"permanentidentifier": "abc123"},
                },
                {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": [[2, 2], [3, 3]]},
                    "properties": {"permanentidentifier": "def456"},
                },
            ],
        }
        result = TNMFeatureCollection.model_validate(collection)
        assert result.type == "FeatureCollection"
        assert len(result.features) == 2

    def test_empty_feature_collection(self):
        """Test empty FeatureCollection is valid."""
        collection = {"type": "FeatureCollection", "features": []}
        result = TNMFeatureCollection.model_validate(collection)
        assert len(result.features) == 0

    def test_invalid_collection_type(self):
        """Test collection with wrong type raises ValidationError."""
        collection = {"type": "InvalidCollection", "features": []}
        with pytest.raises(ValidationError):
            TNMFeatureCollection.model_validate(collection)

    def test_missing_features(self):
        """Test collection without features raises ValidationError."""
        collection = {"type": "FeatureCollection"}
        with pytest.raises(ValidationError):
            TNMFeatureCollection.model_validate(collection)


# =============================================================================
# PANDERA SCHEMA TESTS - Processed GeoDataFrame Validation
# =============================================================================


@pytest.fixture
def valid_tnm_trails_gdf():
    """Create a valid TNM trails GeoDataFrame for testing."""
    data = {
        "permanent_identifier": ["trail1", "trail2", "trail3"],
        "park_code": ["acad", "yell", "zion"],
        "name": ["Precipice Trail", "Old Faithful Trail", "Angels Landing"],
        "length_miles": [1.5, 2.3, 5.4],
        "geometry_type": ["LineString", "LineString", "MultiLineString"],
        "collected_at": ["2024-01-01T00:00:00Z"] * 3,
        "geometry": [
            LineString([(0, 0), (1, 1)]),
            LineString([(1, 1), (2, 2)]),
            MultiLineString([[(2, 2), (3, 3)], [(4, 4), (5, 5)]]),
        ],
    }
    return gpd.GeoDataFrame(data, crs="EPSG:4326")


@pytest.fixture
def valid_tnm_trails_with_optionals_gdf():
    """Create a valid TNM trails GeoDataFrame with optional fields."""
    data = {
        "permanent_identifier": ["trail1"],
        "park_code": ["acad"],
        "name": ["Precipice Trail"],
        "length_miles": [1.5],
        "geometry_type": ["LineString"],
        "collected_at": ["2024-01-01T00:00:00Z"],
        "geometry": [LineString([(0, 0), (1, 1)])],
        # Optional string fields
        "name_alternate": ["Precipice Loop"],
        "trail_number": ["TR-001"],
        "trail_type": ["Terra Trail"],
        "primary_trail_maintainer": ["National Park Service"],
        # Optional boolean fields
        "hiker_pedestrian": ["Y"],
        "bicycle": ["N"],
        "pack_saddle": ["N"],
        "motorcycle": ["N"],
        # Optional numeric fields
        "object_id": [12345],
        "shape_length": [0.05],
    }
    return gpd.GeoDataFrame(data, crs="EPSG:4326")


class TestTNMProcessedTrailsSchema:
    """Test TNM processed trails Pandera schema validation."""

    def test_valid_trails_pass_validation(self, valid_tnm_trails_gdf):
        """Test that valid trail data passes schema validation."""
        # Should not raise exception
        result = TNMProcessedTrailsSchema.validate(valid_tnm_trails_gdf)
        assert len(result) == 3

    def test_valid_trails_with_optionals_pass_validation(
        self, valid_tnm_trails_with_optionals_gdf
    ):
        """Test that valid trail data with optional fields passes validation."""
        result = TNMProcessedTrailsSchema.validate(valid_tnm_trails_with_optionals_gdf)
        assert len(result) == 1
        assert result["name_alternate"].iloc[0] == "Precipice Loop"
        assert result["hiker_pedestrian"].iloc[0] == "Y"

    def test_missing_required_column_fails(self, valid_tnm_trails_gdf):
        """Test that missing required column fails validation."""
        gdf = valid_tnm_trails_gdf.drop(columns=["permanent_identifier"])
        with pytest.raises(SchemaError, match="permanent_identifier"):
            TNMProcessedTrailsSchema.validate(gdf)

    def test_invalid_park_code_length_fails(self, valid_tnm_trails_gdf):
        """Test that park_code not exactly 4 chars fails validation."""
        gdf = valid_tnm_trails_gdf.copy()
        gdf.loc[0, "park_code"] = "abc"  # Only 3 chars
        with pytest.raises(
            (SchemaError, SchemaErrors), match="park_code must be 4 chars"
        ):
            TNMProcessedTrailsSchema.validate(gdf, lazy=True)

    def test_invalid_park_code_case_fails(self, valid_tnm_trails_gdf):
        """Test that park_code with uppercase fails validation."""
        gdf = valid_tnm_trails_gdf.copy()
        gdf.loc[0, "park_code"] = "ACAD"  # Uppercase
        with pytest.raises(
            (SchemaError, SchemaErrors), match="park_code must be lowercase"
        ):
            TNMProcessedTrailsSchema.validate(gdf, lazy=True)

    def test_length_below_minimum_fails(self, valid_tnm_trails_gdf):
        """Test that length_miles below minimum fails validation."""
        gdf = valid_tnm_trails_gdf.copy()
        gdf.loc[0, "length_miles"] = 0.005  # Below 0.01 minimum
        with pytest.raises(
            (SchemaError, SchemaErrors),
            match=f"length_miles must be >= {config.TNM_MIN_TRAIL_LENGTH_MI}",
        ):
            TNMProcessedTrailsSchema.validate(gdf, lazy=True)

    def test_length_above_maximum_fails(self, valid_tnm_trails_gdf):
        """Test that length_miles above maximum fails validation."""
        gdf = valid_tnm_trails_gdf.copy()
        gdf.loc[0, "length_miles"] = 1001  # Above 1000 maximum
        with pytest.raises(
            (SchemaError, SchemaErrors), match="length_miles must be < 1000"
        ):
            TNMProcessedTrailsSchema.validate(gdf, lazy=True)

    def test_invalid_geometry_type_fails(self, valid_tnm_trails_gdf):
        """Test that invalid geometry_type fails validation."""
        gdf = valid_tnm_trails_gdf.copy()
        gdf.loc[0, "geometry_type"] = "Polygon"  # Not LineString/MultiLineString
        with pytest.raises(
            (SchemaError, SchemaErrors),
            match="geometry_type must be LineString or MultiLineString",
        ):
            TNMProcessedTrailsSchema.validate(gdf, lazy=True)

    def test_invalid_geometry_fails(self, valid_tnm_trails_gdf):
        """Test that invalid geometry fails validation."""
        gdf = valid_tnm_trails_gdf.copy()
        gdf.loc[0, "geometry"] = Point(0, 0)  # Point instead of LineString
        with pytest.raises((SchemaError, SchemaErrors), match="Geometry must be"):
            TNMProcessedTrailsSchema.validate(gdf, lazy=True)

    def test_empty_permanent_identifier_fails(self, valid_tnm_trails_gdf):
        """Test that empty permanent_identifier fails validation."""
        gdf = valid_tnm_trails_gdf.copy()
        gdf.loc[0, "permanent_identifier"] = ""
        with pytest.raises(
            (SchemaError, SchemaErrors), match="permanent_identifier cannot be empty"
        ):
            TNMProcessedTrailsSchema.validate(gdf, lazy=True)

    def test_permanent_identifier_too_long_fails(self, valid_tnm_trails_gdf):
        """Test that permanent_identifier over 100 chars fails validation."""
        gdf = valid_tnm_trails_gdf.copy()
        gdf.loc[0, "permanent_identifier"] = "a" * 101
        with pytest.raises(
            (SchemaError, SchemaErrors), match="permanent_identifier max 100 chars"
        ):
            TNMProcessedTrailsSchema.validate(gdf, lazy=True)

    def test_name_too_long_fails(self, valid_tnm_trails_gdf):
        """Test that name over 500 chars fails validation."""
        gdf = valid_tnm_trails_gdf.copy()
        gdf.loc[0, "name"] = "a" * 501
        with pytest.raises((SchemaError, SchemaErrors), match="name max 500 chars"):
            TNMProcessedTrailsSchema.validate(gdf, lazy=True)

    def test_invalid_boolean_field_value_fails(
        self, valid_tnm_trails_with_optionals_gdf
    ):
        """Test that invalid boolean field value fails validation."""
        gdf = valid_tnm_trails_with_optionals_gdf.copy()
        gdf.loc[0, "hiker_pedestrian"] = "Yes"  # Should be "Y" or "N"
        with pytest.raises(
            (SchemaError, SchemaErrors), match="hiker_pedestrian must be Y, N"
        ):
            TNMProcessedTrailsSchema.validate(gdf, lazy=True)

    def test_null_optional_boolean_field_passes(self, valid_tnm_trails_gdf):
        """Test that null values in optional boolean fields pass validation."""
        gdf = valid_tnm_trails_gdf.copy()
        gdf["hiker_pedestrian"] = None
        # Should not raise exception
        result = TNMProcessedTrailsSchema.validate(gdf)
        assert result["hiker_pedestrian"].isna().all()

    def test_pd_na_optional_boolean_field_passes(self, valid_tnm_trails_gdf):
        """Test that pd.NA values in optional boolean fields pass validation."""
        gdf = valid_tnm_trails_gdf.copy()
        gdf["hiker_pedestrian"] = pd.NA
        # Should not raise exception
        result = TNMProcessedTrailsSchema.validate(gdf)
        assert result["hiker_pedestrian"].isna().all()

    def test_missing_optional_columns_passes(self, valid_tnm_trails_gdf):
        """Test that missing optional columns pass validation."""
        # The fixture doesn't have optional columns - should still pass
        result = TNMProcessedTrailsSchema.validate(valid_tnm_trails_gdf)
        assert len(result) == 3

    def test_extra_columns_allowed(self, valid_tnm_trails_gdf):
        """Test that extra columns are allowed (strict=False)."""
        gdf = valid_tnm_trails_gdf.copy()
        gdf["extra_column"] = "extra_value"
        # Should not raise exception due to strict=False
        result = TNMProcessedTrailsSchema.validate(gdf)
        assert "extra_column" in result.columns

    def test_multiple_validation_errors_with_lazy(self, valid_tnm_trails_gdf):
        """Test that lazy validation collects multiple errors."""
        gdf = valid_tnm_trails_gdf.copy()
        gdf.loc[0, "park_code"] = "ABC"  # Wrong case and length
        gdf.loc[1, "length_miles"] = 0.005  # Too short
        gdf.loc[2, "geometry_type"] = "Polygon"  # Wrong type

        with pytest.raises((SchemaError, SchemaErrors)) as exc_info:
            TNMProcessedTrailsSchema.validate(gdf, lazy=True)

        # Check that multiple errors are reported
        error_msg = str(exc_info.value)
        # Should contain multiple validation failures
        assert "park_code" in error_msg or "length_miles" in error_msg


class TestTNMSchemaIntegration:
    """Integration tests for TNM schema validation workflow."""

    def test_api_to_processed_workflow(self):
        """Test the complete workflow from API response to processed data."""
        # Simulate TNM API response
        api_response = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
                    "properties": {
                        "permanentidentifier": "trail123",
                        "name": "Test Trail",
                        "lengthmiles": 2.5,
                    },
                }
            ],
        }

        # Validate API response with Pydantic
        validated_api = TNMFeatureCollection.model_validate(api_response)
        assert len(validated_api.features) == 1
        assert validated_api.features[0].properties.permanentidentifier == "trail123"

        # Simulate conversion to GeoDataFrame (would happen in collector)
        gdf = gpd.GeoDataFrame.from_features(api_response["features"], crs="EPSG:4326")
        gdf["park_code"] = "acad"
        gdf["length_miles"] = 2.5
        gdf["geometry_type"] = "LineString"
        gdf["collected_at"] = "2024-01-01T00:00:00Z"
        gdf = gdf.rename(columns={"permanentidentifier": "permanent_identifier"})

        # Validate processed data with Pandera
        result = TNMProcessedTrailsSchema.validate(gdf)
        assert len(result) == 1
        assert result["permanent_identifier"].iloc[0] == "trail123"

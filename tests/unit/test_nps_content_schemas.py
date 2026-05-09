"""Unit tests for NPS content Pydantic schemas."""

import pytest
from pydantic import ValidationError

from scripts.collectors.nps_content_schemas import (
    NPSPlaceResponse,
    NPSThingsToDoResponse,
    strip_html,
)


class TestStripHtml:
    """Tests for the HTML stripping utility."""

    def test_strips_simple_tags(self):
        assert strip_html("<p>Hello</p>") == "Hello"

    def test_strips_nested_tags(self):
        assert strip_html("<div><b>Bold</b> text</div>") == "Bold text"

    def test_returns_empty_for_empty(self):
        assert strip_html("") == ""

    def test_preserves_plain_text(self):
        assert strip_html("No tags here") == "No tags here"

    def test_collapses_whitespace(self):
        result = strip_html("<p>Line one</p>  <p>Line two</p>")
        assert "  " not in result


class TestNPSThingsToDoSchema:
    """Tests for NPSThingsToDoResponse validation."""

    def test_valid_response_passes(self, sample_thingstodo_api_response):
        item = NPSThingsToDoResponse.model_validate(sample_thingstodo_api_response)
        assert item.id == "ABC123"
        assert item.title == "Hike to Vernal Fall"

    def test_html_stripped_from_descriptions(self, sample_thingstodo_api_response):
        item = NPSThingsToDoResponse.model_validate(sample_thingstodo_api_response)
        assert "<b>" not in (item.short_description or "")
        assert "<p>" not in (item.long_description or "")
        assert "<p>" not in (item.accessibility_information or "")

    def test_missing_required_id_raises(self, sample_thingstodo_api_response):
        del sample_thingstodo_api_response["id"]
        with pytest.raises(ValidationError):
            NPSThingsToDoResponse.model_validate(sample_thingstodo_api_response)

    def test_missing_required_title_raises(self, sample_thingstodo_api_response):
        del sample_thingstodo_api_response["title"]
        with pytest.raises(ValidationError):
            NPSThingsToDoResponse.model_validate(sample_thingstodo_api_response)

    def test_valid_coordinates(self, sample_thingstodo_api_response):
        item = NPSThingsToDoResponse.model_validate(sample_thingstodo_api_response)
        assert item.latitude == "37.7268"
        assert item.longitude == "-119.5428"

    def test_invalid_latitude_set_to_none(self, sample_thingstodo_api_response):
        sample_thingstodo_api_response["latitude"] = "999"
        item = NPSThingsToDoResponse.model_validate(sample_thingstodo_api_response)
        assert item.latitude is None

    def test_missing_coordinates_handled(self, sample_thingstodo_api_response):
        sample_thingstodo_api_response["latitude"] = None
        sample_thingstodo_api_response["longitude"] = None
        item = NPSThingsToDoResponse.model_validate(sample_thingstodo_api_response)
        assert item.latitude is None
        assert item.longitude is None

    def test_empty_tags_handled(self, sample_thingstodo_api_response):
        sample_thingstodo_api_response["tags"] = []
        item = NPSThingsToDoResponse.model_validate(sample_thingstodo_api_response)
        assert item.tags == []

    def test_empty_activities_handled(self, sample_thingstodo_api_response):
        sample_thingstodo_api_response["activities"] = []
        item = NPSThingsToDoResponse.model_validate(sample_thingstodo_api_response)
        assert item.activities == []

    def test_get_park_codes(self, sample_thingstodo_api_response):
        item = NPSThingsToDoResponse.model_validate(sample_thingstodo_api_response)
        codes = item.get_park_codes()
        assert "yose" in codes


class TestNPSPlaceSchema:
    """Tests for NPSPlaceResponse validation."""

    def test_valid_response_passes(self, sample_places_api_response):
        item = NPSPlaceResponse.model_validate(sample_places_api_response)
        assert item.id == "DEF456"
        assert item.title == "Glacier Point"

    def test_html_stripped_from_body(self, sample_places_api_response):
        item = NPSPlaceResponse.model_validate(sample_places_api_response)
        assert "<p>" not in (item.body_text or "")
        assert "<em>" not in (item.short_description or "")

    def test_missing_required_id_raises(self, sample_places_api_response):
        del sample_places_api_response["id"]
        with pytest.raises(ValidationError):
            NPSPlaceResponse.model_validate(sample_places_api_response)

    def test_valid_coordinates(self, sample_places_api_response):
        item = NPSPlaceResponse.model_validate(sample_places_api_response)
        assert item.latitude == "37.7306"

    def test_invalid_longitude_set_to_none(self, sample_places_api_response):
        sample_places_api_response["longitude"] = "999"
        item = NPSPlaceResponse.model_validate(sample_places_api_response)
        assert item.longitude is None

    def test_get_park_codes(self, sample_places_api_response):
        item = NPSPlaceResponse.model_validate(sample_places_api_response)
        codes = item.get_park_codes()
        assert "yose" in codes

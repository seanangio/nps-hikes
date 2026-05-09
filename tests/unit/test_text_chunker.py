"""Unit tests for the text chunking module."""

import pytest

from scripts.processors.text_chunker import (
    MAX_CHUNK_LENGTH,
    chunk_park_description,
    chunk_places,
    chunk_thingstodo,
)


class TestChunkThingsToDo:
    """Tests for chunk_thingstodo."""

    def test_short_content_single_chunk(self):
        record = {
            "id": "ABC123",
            "park_code": "yose",
            "title": "Hike to Vernal Fall",
            "short_description": "A stunning waterfall hike.",
            "long_description": "Follow the Mist Trail to see the 317-foot waterfall.",
            "tags": ["hiking"],
            "season": ["Summer"],
            "duration": "2-3 Hours",
        }
        chunks = chunk_thingstodo(record)
        assert len(chunks) == 1
        assert "Hike to Vernal Fall" in chunks[0]["chunk_text"]
        assert chunks[0]["source_type"] == "thingstodo"
        assert chunks[0]["source_id"] == "ABC123"
        assert chunks[0]["park_code"] == "yose"

    def test_long_content_splits(self):
        # Create text with paragraph breaks that exceeds MAX_CHUNK_LENGTH
        paragraph = "This is a paragraph about a great hiking activity. " * 20
        long_text = "\n\n".join([paragraph] * 5)
        record = {
            "id": "ABC123",
            "park_code": "yose",
            "title": "Long Activity",
            "short_description": "A short description.",
            "long_description": long_text,
        }
        chunks = chunk_thingstodo(record)
        assert len(chunks) > 1

    def test_chunk_includes_title(self):
        record = {
            "id": "ABC123",
            "park_code": "yose",
            "title": "Star Gazing",
            "short_description": "Look at the stars.",
            "long_description": None,
        }
        chunks = chunk_thingstodo(record)
        assert "Star Gazing" in chunks[0]["chunk_text"]

    def test_metadata_extracted(self):
        record = {
            "id": "ABC123",
            "park_code": "yose",
            "title": "Test",
            "short_description": "Desc",
            "long_description": None,
            "tags": ["hiking", "nature"],
            "season": ["Spring"],
            "duration": "1 Hour",
            "activities": ["Hiking"],
            "topics": ["Waterfalls"],
        }
        chunks = chunk_thingstodo(record)
        assert chunks[0]["metadata"]["tags"] == ["hiking", "nature"]
        assert chunks[0]["metadata"]["season"] == ["Spring"]
        assert chunks[0]["metadata"]["duration"] == "1 Hour"

    def test_empty_description_uses_title(self):
        record = {
            "id": "ABC123",
            "park_code": "yose",
            "title": "Title Only",
            "short_description": None,
            "long_description": None,
        }
        chunks = chunk_thingstodo(record)
        assert len(chunks) == 1
        assert "Title Only" in chunks[0]["chunk_text"]

    def test_empty_title_and_description_returns_empty(self):
        record = {
            "id": "ABC123",
            "park_code": "yose",
            "title": "",
            "short_description": None,
            "long_description": None,
        }
        chunks = chunk_thingstodo(record)
        assert chunks == []


class TestChunkPlaces:
    """Tests for chunk_places."""

    def test_short_content_single_chunk(self):
        record = {
            "id": "DEF456",
            "park_code": "yose",
            "title": "Glacier Point",
            "short_description": "A panoramic viewpoint.",
            "body_text": "Offers sweeping views of Yosemite Valley.",
            "tags": ["viewpoint"],
        }
        chunks = chunk_places(record)
        assert len(chunks) == 1
        assert "Glacier Point" in chunks[0]["chunk_text"]
        assert chunks[0]["source_type"] == "places"
        assert chunks[0]["source_id"] == "DEF456"

    def test_metadata_includes_tags(self):
        record = {
            "id": "DEF456",
            "park_code": "yose",
            "title": "Glacier Point",
            "short_description": "A viewpoint.",
            "body_text": None,
            "tags": ["scenic", "viewpoint"],
        }
        chunks = chunk_places(record)
        assert chunks[0]["metadata"]["tags"] == ["scenic", "viewpoint"]

    def test_empty_tags_no_metadata(self):
        record = {
            "id": "DEF456",
            "park_code": "yose",
            "title": "Test Place",
            "short_description": "Desc",
            "body_text": None,
            "tags": [],
        }
        chunks = chunk_places(record)
        assert "tags" not in chunks[0]["metadata"]


class TestChunkParkDescription:
    """Tests for chunk_park_description."""

    def test_normal_description_single_chunk(self):
        chunks = chunk_park_description(
            "yose",
            "Yosemite National Park",
            "A beautiful park with granite cliffs and waterfalls.",
        )
        assert len(chunks) == 1
        assert "Yosemite National Park" in chunks[0]["chunk_text"]
        assert "granite cliffs" in chunks[0]["chunk_text"]
        assert chunks[0]["source_type"] == "park_description"
        assert chunks[0]["park_code"] == "yose"

    def test_empty_description_returns_empty(self):
        chunks = chunk_park_description("yose", "Yosemite", "")
        assert chunks == []

    def test_none_description_returns_empty(self):
        chunks = chunk_park_description("yose", "Yosemite", None)
        assert chunks == []

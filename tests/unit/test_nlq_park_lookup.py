"""Unit tests for NLQ park name to park_code resolution."""

from unittest.mock import patch

import pytest

from api.nlq.park_lookup import (
    build_park_lookup_text,
    clear_park_lookup_cache,
    resolve_park_code,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear the park lookup cache before each test."""
    clear_park_lookup_cache()
    yield
    clear_park_lookup_cache()


@pytest.fixture
def sample_lookup():
    """Provide a sample park lookup dict for testing."""
    return {
        "yose": "yose",
        "yosemite national park": "yose",
        "yosemite": "yose",
        "zion": "zion",
        "zion national park": "zion",
        "romo": "romo",
        "rocky mountain national park": "romo",
        "rocky mountain": "romo",
        "grca": "grca",
        "grand canyon national park": "grca",
        "grand canyon": "grca",
    }


class TestResolveParkCode:
    """Tests for the resolve_park_code function."""

    def test_exact_code_match(self, sample_lookup):
        assert resolve_park_code("yose", sample_lookup) == "yose"

    def test_exact_name_match(self, sample_lookup):
        assert resolve_park_code("Yosemite National Park", sample_lookup) == "yose"

    def test_short_name_match(self, sample_lookup):
        assert resolve_park_code("Yosemite", sample_lookup) == "yose"

    def test_case_insensitive(self, sample_lookup):
        assert resolve_park_code("YOSE", sample_lookup) == "yose"
        assert resolve_park_code("YOSEMITE", sample_lookup) == "yose"

    def test_whitespace_stripped(self, sample_lookup):
        assert resolve_park_code("  yose  ", sample_lookup) == "yose"

    def test_unknown_4char_code_returned_as_is(self, sample_lookup):
        assert resolve_park_code("xxxx", sample_lookup) == "xxxx"

    def test_fuzzy_match(self, sample_lookup):
        # "Yosemit" is close enough to "yosemite"
        assert resolve_park_code("Yosemit", sample_lookup) == "yose"

    def test_fuzzy_match_misspelling(self, sample_lookup):
        assert resolve_park_code("Yosemmite", sample_lookup) == "yose"

    def test_no_match_returns_none(self, sample_lookup):
        assert resolve_park_code("completely unknown park", sample_lookup) is None

    def test_rocky_mountain(self, sample_lookup):
        assert resolve_park_code("Rocky Mountain", sample_lookup) == "romo"

    def test_grand_canyon(self, sample_lookup):
        assert resolve_park_code("Grand Canyon", sample_lookup) == "grca"


class TestBuildParkLookupText:
    """Tests for the build_park_lookup_text function."""

    def test_produces_text_with_arrows(self, sample_lookup):
        text = build_park_lookup_text(sample_lookup)
        assert "→" in text
        assert "yose" in text
        assert "zion" in text

    def test_skips_code_self_mappings(self, sample_lookup):
        text = build_park_lookup_text(sample_lookup)
        lines = text.strip().split("\n")
        # Each line should have a name and a code, not code → code
        for line in lines:
            parts = line.split("→")
            assert len(parts) == 2
            name_part = parts[0].strip().lstrip("- ")
            code_part = parts[1].strip()
            assert name_part != code_part

    def test_sorted_by_code(self, sample_lookup):
        text = build_park_lookup_text(sample_lookup)
        lines = text.strip().split("\n")
        codes = [line.split("→")[1].strip() for line in lines]
        assert codes == sorted(codes)

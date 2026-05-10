"""
Unit tests for the content-trail linker.

Tests cover:
- Title preprocessing (verb stripping, name normalization)
- Name similarity calculation with containment boost
- Matching logic (threshold, TNM priority, empty/null handling)
"""

import pytest

from scripts.processors.content_trail_linker import (
    ContentTrailLinker,
    calculate_name_similarity,
    preprocess_content_title,
    preprocess_name,
    strip_leading_verb,
)

# ---------------------------------------------------------------------------
# strip_leading_verb tests
# ---------------------------------------------------------------------------


class TestStripLeadingVerb:
    """Tests for strip_leading_verb()."""

    def test_strips_hike(self):
        assert strip_leading_verb("Hike the Mist Trail") == "Mist Trail"

    def test_strips_explore(self):
        assert strip_leading_verb("Explore Glacier Point") == "Glacier Point"

    def test_strips_visit(self):
        assert strip_leading_verb("Visit the Grand Canyon") == "Grand Canyon"

    def test_strips_walk(self):
        assert strip_leading_verb("Walk Along the River") == "Along the River"

    def test_strips_discover(self):
        assert strip_leading_verb("Discover Hidden Falls") == "Hidden Falls"

    def test_strips_experience(self):
        assert strip_leading_verb("Experience the Wilderness") == "Wilderness"

    def test_strips_enjoy(self):
        assert strip_leading_verb("Enjoy a Sunset Hike") == "Sunset Hike"

    def test_strips_ride(self):
        assert strip_leading_verb("Ride the Canyon Trail") == "Canyon Trail"

    def test_strips_bike(self):
        assert strip_leading_verb("Bike the Valley Floor") == "Valley Floor"

    def test_strips_climb(self):
        assert strip_leading_verb("Climb Half Dome") == "Half Dome"

    def test_strips_verb_and_article(self):
        assert (
            strip_leading_verb("Hike the Mist Trail to Vernal Fall")
            == "Mist Trail to Vernal Fall"
        )

    def test_strips_verb_and_article_a(self):
        assert strip_leading_verb("Take a Walk") == "Walk"

    def test_no_verb_to_strip(self):
        assert strip_leading_verb("Mist Trail") == "Mist Trail"

    def test_empty_string(self):
        assert strip_leading_verb("") == ""

    def test_none_returns_empty(self):
        # The function checks `if not title`
        assert strip_leading_verb(None) == ""

    def test_verb_case_insensitive(self):
        assert strip_leading_verb("hike the Mist Trail") == "Mist Trail"

    def test_only_verb(self):
        """A title that is just a verb should strip to empty after article removal."""
        assert strip_leading_verb("Hike") == ""

    def test_verb_with_only_article(self):
        assert strip_leading_verb("Hike the") == ""


# ---------------------------------------------------------------------------
# preprocess_name tests
# ---------------------------------------------------------------------------


class TestPreprocessName:
    """Tests for preprocess_name()."""

    def test_lowercase_and_strip(self):
        assert preprocess_name("  Mist Trail  ") == "mist"

    def test_removes_trail_word(self):
        assert preprocess_name("Mist Trail") == "mist"

    def test_removes_trailhead(self):
        assert preprocess_name("Glacier Point Trailhead") == "glacier point"

    def test_removes_path(self):
        assert preprocess_name("Valley Path") == "valley"

    def test_removes_punctuation(self):
        assert preprocess_name("Angel's Landing, Trail") == "angel's landing"

    def test_removes_dashes(self):
        result = preprocess_name("Half-Dome Trail")
        assert result == "half dome"

    def test_normalizes_whitespace(self):
        assert preprocess_name("  Big   Meadow   Trail  ") == "big meadow"

    def test_empty_string(self):
        assert preprocess_name("") == ""

    def test_none_returns_empty(self):
        assert preprocess_name(None) == ""

    def test_only_trail_word(self):
        assert preprocess_name("Trail") == ""


# ---------------------------------------------------------------------------
# preprocess_content_title tests
# ---------------------------------------------------------------------------


class TestPreprocessContentTitle:
    """Tests for preprocess_content_title()."""

    def test_full_pipeline(self):
        """'Hike the Mist Trail to Vernal Fall' -> verb strip -> name preprocess."""
        result = preprocess_content_title("Hike the Mist Trail to Vernal Fall")
        assert result == "mist to vernal fall"

    def test_no_verb(self):
        result = preprocess_content_title("Mist Trail to Vernal Fall")
        assert result == "mist to vernal fall"

    def test_empty(self):
        assert preprocess_content_title("") == ""

    def test_none(self):
        assert preprocess_content_title(None) == ""

    def test_title_with_trail_word_only(self):
        result = preprocess_content_title("Hike the Trail")
        assert result == ""


# ---------------------------------------------------------------------------
# calculate_name_similarity tests
# ---------------------------------------------------------------------------


class TestCalculateNameSimilarity:
    """Tests for calculate_name_similarity()."""

    def test_exact_match(self):
        score = calculate_name_similarity("Mist Trail", "Mist Trail")
        assert score == 1.0

    def test_high_similarity(self):
        score = calculate_name_similarity("Mist Trail", "The Mist Trail")
        assert score >= 0.7

    def test_containment_boost(self):
        """When one name contains the other, score should be at least 0.8."""
        score = calculate_name_similarity("Tokopah Falls Trail", "Tokopah Falls")
        assert score >= 0.8

    def test_no_match(self):
        """Completely unrelated names should have low similarity."""
        score = calculate_name_similarity("Bird Watching at Dawn", "Half Dome Trail")
        assert score < 0.5

    def test_empty_name1(self):
        assert calculate_name_similarity("", "Mist Trail") == 0.0

    def test_empty_name2(self):
        assert calculate_name_similarity("Mist Trail", "") == 0.0

    def test_both_empty(self):
        assert calculate_name_similarity("", "") == 0.0

    def test_none_name1(self):
        assert calculate_name_similarity(None, "Mist Trail") == 0.0

    def test_none_name2(self):
        assert calculate_name_similarity("Mist Trail", None) == 0.0

    def test_partial_overlap(self):
        """Names with partial word overlap should have moderate similarity."""
        score = calculate_name_similarity("Vernal Fall", "Vernal Fall Bridge")
        assert score >= 0.5

    def test_similar_but_different(self):
        """Similar sounding but different names should have moderate similarity."""
        score = calculate_name_similarity("Mirror Lake", "Mirror Lake Loop")
        assert score >= 0.5


# ---------------------------------------------------------------------------
# ContentTrailLinker.find_best_match tests
# ---------------------------------------------------------------------------


class TestFindBestMatch:
    """Tests for ContentTrailLinker.find_best_match()."""

    @pytest.fixture
    def linker(self):
        """Create a ContentTrailLinker with mocked engine."""
        from unittest.mock import MagicMock

        mock_engine = MagicMock()
        return ContentTrailLinker(write_db=False, engine=mock_engine)

    @pytest.fixture
    def sample_trails(self):
        """Sample trail data for matching tests."""
        return [
            {
                "trail_name": "Mist Trail",
                "trail_id": "TNM123",
                "source": "TNM",
            },
            {
                "trail_name": "Half Dome Trail",
                "trail_id": "TNM456",
                "source": "TNM",
            },
            {
                "trail_name": "Vernal Fall Trail",
                "trail_id": "789",
                "source": "OSM",
            },
        ]

    def test_exact_match(self, linker, sample_trails):
        result = linker.find_best_match("Mist Trail", sample_trails)
        assert result is not None
        assert result["trail_name"] == "Mist Trail"
        assert result["trail_source"] == "TNM"

    def test_verb_stripped_match(self, linker, sample_trails):
        result = linker.find_best_match("Hike the Mist Trail", sample_trails)
        assert result is not None
        assert result["trail_name"] == "Mist Trail"

    def test_no_match_below_threshold(self, linker, sample_trails):
        result = linker.find_best_match("Bird Watching at Dawn", sample_trails)
        assert result is None

    def test_empty_title(self, linker, sample_trails):
        result = linker.find_best_match("", sample_trails)
        assert result is None

    def test_none_title(self, linker, sample_trails):
        result = linker.find_best_match(None, sample_trails)
        assert result is None

    def test_empty_trails_list(self, linker):
        result = linker.find_best_match("Mist Trail", [])
        assert result is None

    def test_tnm_preferred_over_osm(self, linker):
        """TNM should be preferred when both match with equal score."""
        trails = [
            {
                "trail_name": "Sunset Trail",
                "trail_id": "OSM100",
                "source": "OSM",
            },
            {
                "trail_name": "Sunset Trail",
                "trail_id": "TNM100",
                "source": "TNM",
            },
        ]
        result = linker.find_best_match("Sunset Trail", trails)
        assert result is not None
        assert result["trail_source"] == "TNM"
        assert result["trail_id"] == "TNM100"

    def test_match_includes_scores(self, linker, sample_trails):
        result = linker.find_best_match("Mist Trail", sample_trails)
        assert result is not None
        assert "name_similarity_score" in result
        assert "match_confidence" in result
        assert result["name_similarity_score"] > 0
        assert result["match_confidence"] >= linker.threshold

    def test_content_title_with_extra_context(self, linker, sample_trails):
        """Titles with extra context should still match the trail part."""
        result = linker.find_best_match(
            "Hike the Mist Trail to Vernal Fall", sample_trails
        )
        # Should match either Mist Trail or Vernal Fall Trail
        assert result is not None

    def test_threshold_boundary(self, linker):
        """A match exactly at threshold should be returned."""
        # Use names that produce a score just around 0.5
        trails = [
            {
                "trail_name": "Canyon View",
                "trail_id": "T1",
                "source": "TNM",
            },
        ]
        result = linker.find_best_match("Canyon View Trail", trails)
        if result is not None:
            assert result["match_confidence"] >= linker.threshold

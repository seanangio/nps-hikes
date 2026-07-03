"""Unit tests for NLQ response parsing and parameter validation."""

import pytest

from api.nlq.parser import parse_tool_call, validate_and_normalize
from utils.exceptions import LlmResponseError


@pytest.fixture
def park_lookup():
    """Sample park lookup for testing."""
    return {
        "yose": "yose",
        "yosemite national park": "yose",
        "yosemite": "yose",
        "zion": "zion",
        "zion national park": "zion",
        "romo": "romo",
        "rocky mountain": "romo",
    }


class TestParseToolCall:
    """Tests for extracting tool calls from Ollama responses."""

    def test_standard_tool_calls_format(self):
        """Test parsing standard Ollama tool_calls response."""
        response = {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "search_trails",
                            "arguments": {
                                "park_code": "yose",
                                "min_length": 5.0,
                            },
                        }
                    }
                ],
            }
        }
        name, args = parse_tool_call(response)
        assert name == "search_trails"
        assert args == {"park_code": "yose", "min_length": 5.0}

    def test_tool_calls_with_no_arguments(self):
        """Test parsing tool call with empty arguments."""
        response = {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "search_parks",
                            "arguments": {},
                        }
                    }
                ],
            }
        }
        name, args = parse_tool_call(response)
        assert name == "search_parks"
        assert args == {}

    def test_json_in_content_fallback(self):
        """Test fallback parsing of JSON in message content."""
        response = {
            "message": {
                "role": "assistant",
                "content": '{"function": "search_trails", "arguments": {"park_code": "zion"}}',
            }
        }
        name, args = parse_tool_call(response)
        assert name == "search_trails"
        assert args == {"park_code": "zion"}

    def test_json_in_markdown_code_block(self):
        """Test extraction from markdown code fences."""
        response = {
            "message": {
                "role": "assistant",
                "content": 'Here is the call:\n```json\n{"function": "search_parks", "arguments": {"visited": true}}\n```',
            }
        }
        name, args = parse_tool_call(response)
        assert name == "search_parks"
        assert args == {"visited": True}

    def test_raises_on_empty_response(self):
        """Test that empty responses raise LlmResponseError."""
        response = {"message": {"role": "assistant", "content": ""}}
        with pytest.raises(LlmResponseError):
            parse_tool_call(response)

    def test_raises_on_no_function_name(self):
        """Test that responses without a function name raise error."""
        response = {
            "message": {
                "role": "assistant",
                "content": "I can help you find trails in Yosemite!",
            }
        }
        with pytest.raises(LlmResponseError):
            parse_tool_call(response)

    def test_raises_on_missing_message(self):
        """Test that responses without a message key raise error."""
        response = {}
        with pytest.raises(LlmResponseError):
            parse_tool_call(response)

    def test_alternative_key_names(self):
        """Test that alternative JSON key names are handled."""
        response = {
            "message": {
                "role": "assistant",
                "content": '{"name": "search_trails", "parameters": {"park_code": "yose"}}',
            }
        }
        name, args = parse_tool_call(response)
        assert name == "search_trails"
        assert args == {"park_code": "yose"}


class TestValidateAndNormalize:
    """Tests for parameter validation and normalization."""

    def test_valid_trail_params_pass_through(self, park_lookup):
        name, params = validate_and_normalize(
            "search_trails",
            {"park_code": "yose", "min_length": 5.0, "hiked": True},
            park_lookup,
        )
        assert name == "search_trails"
        assert params == {"park_code": "yose", "min_length": 5.0, "hiked": True}

    def test_uppercase_park_code_lowercased(self, park_lookup):
        _, params = validate_and_normalize(
            "search_trails",
            {"park_code": "YOSE"},
            park_lookup,
        )
        assert params["park_code"] == "yose"

    def test_park_name_resolved_to_code(self, park_lookup):
        _, params = validate_and_normalize(
            "search_trails",
            {"park_code": "Yosemite"},
            park_lookup,
        )
        assert params["park_code"] == "yose"

    def test_full_park_name_resolved(self, park_lookup):
        _, params = validate_and_normalize(
            "search_trails",
            {"park_code": "Yosemite National Park"},
            park_lookup,
        )
        assert params["park_code"] == "yose"

    def test_state_name_to_code(self, park_lookup):
        _, params = validate_and_normalize(
            "search_trails",
            {"state": "California"},
            park_lookup,
        )
        assert params["state"] == "CA"

    def test_state_code_uppercased(self, park_lookup):
        _, params = validate_and_normalize(
            "search_trails",
            {"state": "ca"},
            park_lookup,
        )
        assert params["state"] == "CA"

    def test_source_uppercased(self, park_lookup):
        _, params = validate_and_normalize(
            "search_trails",
            {"source": "tnm"},
            park_lookup,
        )
        assert params["source"] == "TNM"

    def test_invalid_source_dropped(self, park_lookup):
        _, params = validate_and_normalize(
            "search_trails",
            {"source": "invalid"},
            park_lookup,
        )
        assert "source" not in params

    def test_length_clamped_to_range(self, park_lookup):
        _, params = validate_and_normalize(
            "search_trails",
            {"min_length": -5.0, "max_length": 200.0},
            park_lookup,
        )
        assert params["min_length"] == 0.0
        assert params["max_length"] == 100.0

    def test_limit_clamped(self, park_lookup):
        _, params = validate_and_normalize(
            "search_trails",
            {"limit": 5000},
            park_lookup,
        )
        assert params["limit"] == 1000

    def test_empty_params_return_empty(self, park_lookup):
        _, params = validate_and_normalize(
            "search_trails",
            {},
            park_lookup,
        )
        assert params == {}

    def test_search_parks_visited_true(self, park_lookup):
        name, params = validate_and_normalize(
            "search_parks",
            {"visited": True},
            park_lookup,
        )
        assert name == "search_parks"
        assert params == {"visited": True}

    def test_search_parks_empty_params(self, park_lookup):
        _, params = validate_and_normalize(
            "search_parks",
            {},
            park_lookup,
        )
        assert params == {}

    # --- search_parks visit_year / visit_month ---

    def test_search_parks_visit_year_valid(self, park_lookup):
        _, params = validate_and_normalize(
            "search_parks", {"visit_year": 2024}, park_lookup
        )
        assert params == {"visit_year": 2024, "visited": True}

    def test_search_parks_visit_year_string_coerced(self, park_lookup):
        _, params = validate_and_normalize(
            "search_parks", {"visit_year": "2024"}, park_lookup
        )
        assert params == {"visit_year": 2024, "visited": True}

    def test_search_parks_visit_year_out_of_range_dropped(self, park_lookup):
        _, params = validate_and_normalize(
            "search_parks", {"visit_year": 1800}, park_lookup
        )
        assert "visit_year" not in params

    def test_search_parks_visit_month_full_name(self, park_lookup):
        _, params = validate_and_normalize(
            "search_parks", {"visit_month": "October"}, park_lookup
        )
        assert params["visit_month"] == ["Oct", "October"]

    def test_search_parks_visit_month_abbreviation(self, park_lookup):
        _, params = validate_and_normalize(
            "search_parks", {"visit_month": "Oct"}, park_lookup
        )
        assert params["visit_month"] == ["Oct", "October"]

    def test_search_parks_visit_month_numeric(self, park_lookup):
        _, params = validate_and_normalize(
            "search_parks", {"visit_month": "10"}, park_lookup
        )
        assert params["visit_month"] == ["Oct", "October"]

    def test_search_parks_visit_month_season_summer(self, park_lookup):
        _, params = validate_and_normalize(
            "search_parks", {"visit_month": "summer"}, park_lookup
        )
        assert params["visit_month"] == ["Jun", "June", "Jul", "July", "Aug", "August"]

    def test_search_parks_visit_month_season_winter(self, park_lookup):
        _, params = validate_and_normalize(
            "search_parks", {"visit_month": "winter"}, park_lookup
        )
        assert params["visit_month"] == [
            "Dec",
            "December",
            "Jan",
            "January",
            "Feb",
            "February",
        ]

    def test_search_parks_visit_month_season_fall(self, park_lookup):
        _, params = validate_and_normalize(
            "search_parks", {"visit_month": "fall"}, park_lookup
        )
        assert params["visit_month"] == [
            "Sep",
            "September",
            "Oct",
            "October",
            "Nov",
            "November",
        ]

    def test_search_parks_visit_month_season_autumn_alias(self, park_lookup):
        _, params = validate_and_normalize(
            "search_parks", {"visit_month": "autumn"}, park_lookup
        )
        assert params["visit_month"] == [
            "Sep",
            "September",
            "Oct",
            "October",
            "Nov",
            "November",
        ]

    def test_search_parks_visit_month_invalid_dropped(self, park_lookup):
        _, params = validate_and_normalize(
            "search_parks", {"visit_month": "notamonth"}, park_lookup
        )
        assert "visit_month" not in params

    def test_search_parks_visit_month_case_insensitive(self, park_lookup):
        _, params = validate_and_normalize(
            "search_parks", {"visit_month": "JULY"}, park_lookup
        )
        assert params["visit_month"] == ["Jul", "July"]

    def test_search_parks_may_single_value(self, park_lookup):
        """May is both 3-letter and full name, so only one value."""
        _, params = validate_and_normalize(
            "search_parks", {"visit_month": "May"}, park_lookup
        )
        assert params["visit_month"] == ["May"]

    def test_search_parks_visit_year_and_month_combined(self, park_lookup):
        _, params = validate_and_normalize(
            "search_parks",
            {"visit_year": 2024, "visit_month": "summer", "visited": True},
            park_lookup,
        )
        assert params["visit_year"] == 2024
        assert params["visited"] is True
        assert "Jun" in params["visit_month"]

    def test_search_parks_visit_year_infers_visited(self, park_lookup):
        """visit_year without explicit visited should infer visited=True."""
        _, params = validate_and_normalize(
            "search_parks", {"visit_year": 2024}, park_lookup
        )
        assert params["visit_year"] == 2024
        assert params["visited"] is True

    def test_search_parks_visit_month_infers_visited(self, park_lookup):
        """visit_month without explicit visited should infer visited=True."""
        _, params = validate_and_normalize(
            "search_parks", {"visit_month": "October"}, park_lookup
        )
        assert params["visit_month"] == ["Oct", "October"]
        assert params["visited"] is True

    def test_search_parks_visited_false_not_overridden(self, park_lookup):
        """Explicit visited=False should not be overridden by inference."""
        _, params = validate_and_normalize(
            "search_parks", {"visit_year": 2024, "visited": False}, park_lookup
        )
        assert params["visited"] is False

    def test_unknown_function_raises(self, park_lookup):
        with pytest.raises(LlmResponseError, match="Unknown function"):
            validate_and_normalize("unknown_function", {}, park_lookup)

    def test_none_values_excluded(self, park_lookup):
        _, params = validate_and_normalize(
            "search_trails",
            {"park_code": None, "min_length": None, "state": None},
            park_lookup,
        )
        assert params == {}

    # --- search_stats ---

    def test_search_stats_valid(self, park_lookup):
        name, params = validate_and_normalize(
            "search_stats",
            {"hiked": True},
            park_lookup,
        )
        assert name == "search_stats"
        assert params == {"hiked": True}

    def test_search_stats_per_park_coerced(self, park_lookup):
        _, params = validate_and_normalize(
            "search_stats",
            {"per_park": 1},
            park_lookup,
        )
        assert params["per_park"] is True

    def test_search_stats_empty_params(self, park_lookup):
        _, params = validate_and_normalize(
            "search_stats",
            {},
            park_lookup,
        )
        assert params == {}

    # --- search_park_summary ---

    def test_search_park_summary_valid(self, park_lookup):
        name, params = validate_and_normalize(
            "search_park_summary",
            {"park_code": "yose"},
            park_lookup,
        )
        assert name == "search_park_summary"
        assert params == {"park_code": "yose"}

    def test_search_park_summary_name_resolved(self, park_lookup):
        _, params = validate_and_normalize(
            "search_park_summary",
            {"park_code": "Yosemite"},
            park_lookup,
        )
        assert params["park_code"] == "yose"

    def test_search_park_summary_missing_park_code_raises(self, park_lookup):
        with pytest.raises(LlmResponseError, match="requires a park_code"):
            validate_and_normalize(
                "search_park_summary",
                {},
                park_lookup,
            )

    def test_search_park_summary_none_park_code_raises(self, park_lookup):
        with pytest.raises(LlmResponseError, match="requires a park_code"):
            validate_and_normalize(
                "search_park_summary",
                {"park_code": None},
                park_lookup,
            )

    def test_search_park_summary_unresolvable_raises(self, park_lookup):
        with pytest.raises(LlmResponseError, match="Could not resolve"):
            validate_and_normalize(
                "search_park_summary",
                {"park_code": "xyzxyzxyz"},
                park_lookup,
            )

    # --- negation correction ---

    def test_negation_flips_visited_true_to_false(self, park_lookup):
        """'haven't visited' should flip visited from True to False."""
        _, params = validate_and_normalize(
            "search_parks",
            {"visited": True},
            park_lookup,
            query="Parks I haven't visited",
        )
        assert params["visited"] is False

    def test_negation_flips_hiked_true_to_false(self, park_lookup):
        """'haven't hiked' should flip hiked from True to False."""
        _, params = validate_and_normalize(
            "search_trails",
            {"hiked": True},
            park_lookup,
            query="Trails I haven't hiked yet",
        )
        assert params["hiked"] is False

    def test_negation_never_flips_visited(self, park_lookup):
        """'never been to' should flip visited from True to False."""
        _, params = validate_and_normalize(
            "search_parks",
            {"visited": True},
            park_lookup,
            query="Which parks have I never been to?",
        )
        assert params["visited"] is False

    def test_negation_unvisited_flips_visited(self, park_lookup):
        """'unvisited' should flip visited from True to False."""
        _, params = validate_and_normalize(
            "search_parks",
            {"visited": True},
            park_lookup,
            query="Unvisited national parks",
        )
        assert params["visited"] is False

    def test_negation_stats_hiked_false(self, park_lookup):
        """'haven't hiked' in stats context should flip hiked."""
        _, params = validate_and_normalize(
            "search_stats",
            {"hiked": True},
            park_lookup,
            query="Stats for trails I haven't hiked",
        )
        assert params["hiked"] is False

    def test_no_negation_preserves_true(self, park_lookup):
        """Queries without negation should not flip booleans."""
        _, params = validate_and_normalize(
            "search_parks",
            {"visited": True},
            park_lookup,
            query="Parks I have visited",
        )
        assert params["visited"] is True

    # --- search_by_topic ---

    def test_search_by_topic_valid_query(self, park_lookup):
        name, params = validate_and_normalize(
            "search_by_topic",
            {"query": "waterfalls"},
            park_lookup,
        )
        assert name == "search_by_topic"
        assert params["query"] == "waterfalls"

    def test_search_by_topic_missing_query_raises(self, park_lookup):
        with pytest.raises(LlmResponseError, match="requires a query"):
            validate_and_normalize(
                "search_by_topic",
                {},
                park_lookup,
            )

    def test_search_by_topic_empty_query_raises(self, park_lookup):
        with pytest.raises(LlmResponseError, match="requires a query"):
            validate_and_normalize(
                "search_by_topic",
                {"query": "   "},
                park_lookup,
            )

    def test_search_by_topic_park_code_resolved(self, park_lookup):
        _, params = validate_and_normalize(
            "search_by_topic",
            {"query": "waterfalls", "park_code": "Yosemite"},
            park_lookup,
        )
        assert params["park_code"] == "yose"

    def test_search_by_topic_unknown_park_code_dropped(self, park_lookup):
        _, params = validate_and_normalize(
            "search_by_topic",
            {"query": "waterfalls", "park_code": "xyzxyzxyz"},
            park_lookup,
        )
        assert "park_code" not in params

    def test_search_by_topic_limit_clamped(self, park_lookup):
        _, params = validate_and_normalize(
            "search_by_topic",
            {"query": "waterfalls", "limit": 100},
            park_lookup,
        )
        assert params["limit"] == 50

    def test_search_by_topic_limit_min(self, park_lookup):
        _, params = validate_and_normalize(
            "search_by_topic",
            {"query": "waterfalls", "limit": 0},
            park_lookup,
        )
        assert params["limit"] == 1

    def test_search_by_topic_state_name_resolved(self, park_lookup):
        _, params = validate_and_normalize(
            "search_by_topic",
            {"query": "waterfalls", "state": "California"},
            park_lookup,
        )
        assert params["state"] == "CA"

    def test_search_by_topic_state_code_uppercased(self, park_lookup):
        _, params = validate_and_normalize(
            "search_by_topic",
            {"query": "waterfalls", "state": "ca"},
            park_lookup,
        )
        assert params["state"] == "CA"

    def test_search_by_topic_invalid_state_dropped(self, park_lookup):
        _, params = validate_and_normalize(
            "search_by_topic",
            {"query": "waterfalls", "state": "XYZ"},
            park_lookup,
        )
        assert "state" not in params

    def test_no_negation_hiked_preserves_true(self, park_lookup):
        """Queries without negation should not flip hiked."""
        _, params = validate_and_normalize(
            "search_trails",
            {"park_code": "yose", "hiked": True},
            park_lookup,
            query="Trails I've hiked in Yosemite",
        )
        assert params["hiked"] is True

    def test_negation_no_query_is_noop(self, park_lookup):
        """Without a query string, negation correction is skipped."""
        _, params = validate_and_normalize(
            "search_parks", {"visited": True}, park_lookup
        )
        assert params["visited"] is True


class TestHallucinationValidation:
    """Tests for post-processing validation that removes hallucinated params.

    These tests verify that _validate_extracted_params (called via
    validate_and_normalize for search_by_topic) removes parameters
    the LLM added without textual evidence in the query.
    """

    def test_removes_hallucinated_park_code(self, park_lookup):
        """park_code removed when no park name in query."""
        _, params = validate_and_normalize(
            "search_by_topic",
            {"query": "slot canyons", "park_code": "arch"},
            park_lookup,
            query="slot canyons",
        )
        assert "park_code" not in params
        assert params["query"] == "slot canyons"

    def test_keeps_park_code_when_park_mentioned(self, park_lookup):
        """park_code kept when park name appears in query."""
        _, params = validate_and_normalize(
            "search_by_topic",
            {"query": "waterfalls", "park_code": "yose"},
            park_lookup,
            query="waterfalls in yosemite",
        )
        assert params["park_code"] == "yose"

    def test_removes_hallucinated_source(self, park_lookup):
        """source removed when not mentioned in query."""
        _, params = validate_and_normalize(
            "search_by_topic",
            {"query": "slot canyons", "source": "TNM"},
            park_lookup,
            query="slot canyons in Utah",
        )
        assert "source" not in params

    def test_keeps_source_when_mentioned(self, park_lookup):
        """source kept when explicitly mentioned."""
        _, params = validate_and_normalize(
            "search_by_topic",
            {"query": "trails", "source": "OSM"},
            park_lookup,
            query="OSM trails with viewpoints",
        )
        assert params["source"] == "OSM"

    def test_keeps_source_when_usgs_mentioned(self, park_lookup):
        """source kept when USGS is mentioned (maps to TNM)."""
        _, params = validate_and_normalize(
            "search_by_topic",
            {"query": "trails", "source": "TNM"},
            park_lookup,
            query="USGS trails with waterfalls",
        )
        assert params["source"] == "TNM"

    def test_removes_hallucinated_hiked(self, park_lookup):
        """hiked removed when no completion status in query."""
        _, params = validate_and_normalize(
            "search_by_topic",
            {"query": "slot canyons", "hiked": True},
            park_lookup,
            query="slot canyons",
        )
        assert "hiked" not in params

    def test_keeps_hiked_when_mentioned(self, park_lookup):
        """hiked kept when user mentions hiking status."""
        _, params = validate_and_normalize(
            "search_by_topic",
            {"query": "waterfalls", "hiked": True},
            park_lookup,
            query="waterfall hikes I completed",
        )
        assert params["hiked"] is True

    def test_keeps_hiked_false_when_negation(self, park_lookup):
        """hiked=False kept when user says 'haven't hiked'."""
        _, params = validate_and_normalize(
            "search_by_topic",
            {"query": "slot canyons", "hiked": True},
            park_lookup,
            query="slot canyons I haven't hiked",
        )
        # hiked term present → kept by validation, then flipped by negation
        assert params["hiked"] is False

    def test_removes_zero_min_length(self, park_lookup):
        """min_length=0 is nonsensical and removed."""
        _, params = validate_and_normalize(
            "search_by_topic",
            {"query": "slot canyons", "min_length": 0.0},
            park_lookup,
            query="slot canyons",
        )
        assert "min_length" not in params

    def test_removes_zero_max_length(self, park_lookup):
        """max_length=0 is nonsensical and removed."""
        _, params = validate_and_normalize(
            "search_by_topic",
            {"query": "slot canyons", "max_length": 0.0},
            park_lookup,
            query="slot canyons",
        )
        assert "max_length" not in params

    def test_removes_length_when_not_mentioned(self, park_lookup):
        """Length filters removed when no length terms in query."""
        _, params = validate_and_normalize(
            "search_by_topic",
            {"query": "waterfalls", "min_length": 5.0},
            park_lookup,
            query="waterfalls in the park",
        )
        assert "min_length" not in params

    def test_keeps_length_when_miles_mentioned(self, park_lookup):
        """Length filters kept when 'miles' appears in query."""
        _, params = validate_and_normalize(
            "search_by_topic",
            {"query": "waterfalls", "min_length": 5.0},
            park_lookup,
            query="waterfall hikes over 5 miles",
        )
        assert params["min_length"] == 5.0

    def test_keeps_length_when_long_mentioned(self, park_lookup):
        """Length filters kept when 'long' appears in query."""
        _, params = validate_and_normalize(
            "search_by_topic",
            {"query": "slot canyons", "min_length": 5.0},
            park_lookup,
            query="long slot canyon trails",
        )
        assert params["min_length"] == 5.0

    def test_swaps_max_to_min_for_long_query(self, park_lookup):
        """max_length swapped to min_length when user said 'long'."""
        _, params = validate_and_normalize(
            "search_by_topic",
            {"query": "slot canyons", "max_length": 100.0},
            park_lookup,
            query="long slot canyon trails",
        )
        assert "max_length" not in params
        assert params["min_length"] == 100.0

    def test_removes_multiple_hallucinations(self, park_lookup):
        """Multiple hallucinated params removed at once."""
        _, params = validate_and_normalize(
            "search_by_topic",
            {
                "query": "slot canyons",
                "state": "Utah",
                "park_code": "arch",
                "source": "OSM",
                "hiked": False,
                "min_length": 0.0,
                "max_length": 0.0,
            },
            park_lookup,
            query="slot canyons in Utah",
        )
        assert "park_code" not in params
        assert "source" not in params
        assert "hiked" not in params
        assert "min_length" not in params
        assert "max_length" not in params
        assert params["query"] == "slot canyons"
        assert params["state"] == "UT"

    def test_no_filters_preserved(self, park_lookup):
        """Query with no hallucinated params passes through unchanged."""
        _, params = validate_and_normalize(
            "search_by_topic",
            {"query": "waterfalls"},
            park_lookup,
            query="waterfalls",
        )
        assert params == {"query": "waterfalls"}

    def test_validation_only_applies_to_search_by_topic(self, park_lookup):
        """search_trails does not get hallucination validation."""
        _, params = validate_and_normalize(
            "search_trails",
            {"park_code": "arch", "source": "OSM"},
            park_lookup,
            query="slot canyons",
        )
        # search_trails doesn't run _validate_extracted_params,
        # so these params are preserved even without query evidence
        assert params.get("source") == "OSM"

    def test_validation_skipped_without_query(self, park_lookup):
        """Without a query string, validation is skipped entirely."""
        _, params = validate_and_normalize(
            "search_by_topic",
            {"query": "waterfalls", "park_code": "yose", "source": "TNM"},
            park_lookup,
        )
        # No query → no validation → params preserved
        assert params["park_code"] == "yose"
        assert params["source"] == "TNM"

    def test_realistic_waterfall_hikes_completed_california(self, park_lookup):
        """Realistic test: 'waterfall hikes I completed in California'."""
        _, params = validate_and_normalize(
            "search_by_topic",
            {
                "query": "waterfall hikes",
                "park_code": "wica",
                "state": "California",
                "hiked": True,
            },
            park_lookup,
            query="waterfall hikes I completed in California",
        )
        assert "park_code" not in params  # wica hallucinated
        assert params["state"] == "CA"
        assert params["hiked"] is True
        assert params["query"] == "waterfall hikes"

    def test_realistic_long_slot_canyons(self, park_lookup):
        """Realistic test: 'long slot canyon trails'."""
        _, params = validate_and_normalize(
            "search_by_topic",
            {
                "query": "slot canyon trails",
                "park_code": "arch",
                "max_length": 100.0,
                "source": "OSM",
                "hiked": False,
            },
            park_lookup,
            query="long slot canyon trails",
        )
        assert "park_code" not in params
        assert "source" not in params
        assert "hiked" not in params
        assert "max_length" not in params  # swapped to min_length
        assert params["min_length"] == 100.0

    def test_realistic_slot_canyons_utah(self, park_lookup):
        """Realistic test: 'slot canyons in Utah'."""
        _, params = validate_and_normalize(
            "search_by_topic",
            {
                "query": "slot canyons",
                "state": "Utah",
                "source": "TNM",
                "hiked": True,
                "min_length": 0.0,
                "max_length": 0.0,
            },
            park_lookup,
            query="slot canyons in Utah",
        )
        assert params["state"] == "UT"
        assert "source" not in params
        assert "hiked" not in params
        assert "min_length" not in params
        assert "max_length" not in params

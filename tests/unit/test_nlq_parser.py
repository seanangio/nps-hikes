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

    def test_valid_trail_type_kept(self, park_lookup):
        _, params = validate_and_normalize(
            "search_trails",
            {"trail_type": "footway"},
            park_lookup,
        )
        assert params["trail_type"] == "footway"

    def test_invalid_trail_type_dropped(self, park_lookup):
        _, params = validate_and_normalize(
            "search_trails",
            {"trail_type": "highway"},
            park_lookup,
        )
        assert "trail_type" not in params

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

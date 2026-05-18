"""Unit tests for NLQ generation (prose answers from context chunks)."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from api.nlq.generator import _format_context, generate_from_context
from utils.exceptions import LlmConnectionError


@pytest.fixture
def sample_chunks():
    """Sample context chunks for testing."""
    return [
        {
            "title": "Junior Ranger Program",
            "chunk_text": "Kids can earn a Junior Ranger badge by completing activities.",
            "park_code": "yose",
            "park_name": "Yosemite National Park",
            "source_type": "thingstodo",
            "similarity_score": 0.85,
        },
        {
            "title": "Ranger-Led Walks",
            "chunk_text": "Join a ranger for a guided walk through the valley.",
            "park_code": "grca",
            "park_name": "Grand Canyon National Park",
            "source_type": "thingstodo",
            "similarity_score": 0.78,
        },
    ]


class TestFormatContext:
    """Tests for _format_context helper."""

    def test_formats_chunks_with_park_and_title(self, sample_chunks):
        result = _format_context(sample_chunks)
        assert "[1] Yosemite National Park - Junior Ranger Program" in result
        assert "[2] Grand Canyon National Park - Ranger-Led Walks" in result

    def test_includes_chunk_text(self, sample_chunks):
        result = _format_context(sample_chunks)
        assert "Kids can earn a Junior Ranger badge" in result
        assert "Join a ranger for a guided walk" in result

    def test_empty_chunks_returns_empty_string(self):
        result = _format_context([])
        assert result == ""

    def test_falls_back_to_park_code_when_no_name(self):
        chunks = [
            {
                "title": "Some Title",
                "chunk_text": "Some text",
                "park_code": "yose",
                "source_type": "places",
                "similarity_score": 0.8,
            }
        ]
        result = _format_context(chunks)
        assert "[1] yose - Some Title" in result

    def test_falls_back_to_untitled_when_no_title(self):
        chunks = [
            {
                "chunk_text": "Some text",
                "park_code": "yose",
                "park_name": "Yosemite National Park",
                "source_type": "places",
                "similarity_score": 0.8,
            }
        ]
        result = _format_context(chunks)
        assert "Untitled" in result

    def test_chunks_separated_by_blank_lines(self, sample_chunks):
        result = _format_context(sample_chunks)
        assert "\n\n" in result

    def test_formats_topic_context_shaped_chunks(self):
        """_format_context should work with topic-context-shaped input
        (transformed at the call site in main.py for always-generate)."""
        chunks = [
            {
                "park_name": "Yosemite National Park",
                "title": "Hike to Vernal Fall",
                "chunk_text": "Follow the Mist Trail to see the 317-foot waterfall.",
            },
            {
                "park_name": "Zion National Park",
                "title": "Angels Landing",
                "chunk_text": "A strenuous hike with chain-assisted switchbacks.",
            },
        ]
        result = _format_context(chunks)
        assert "[1] Yosemite National Park - Hike to Vernal Fall" in result
        assert "317-foot waterfall" in result
        assert "[2] Zion National Park - Angels Landing" in result
        assert "chain-assisted switchbacks" in result


class TestGenerateFromContext:
    """Tests for generate_from_context."""

    def test_returns_generated_answer(self, sample_chunks):
        with patch(
            "api.nlq.generator.generate_completion",
            new_callable=AsyncMock,
            return_value="Yosemite offers Junior Ranger programs for kids.",
        ):
            result = asyncio.run(
                generate_from_context("ranger programs for kids", sample_chunks)
            )
            assert result == "Yosemite offers Junior Ranger programs for kids."

    def test_returns_none_on_empty_chunks(self):
        result = asyncio.run(generate_from_context("some query", []))
        assert result is None

    def test_returns_none_on_ollama_unavailable(self, sample_chunks):
        with patch(
            "api.nlq.generator.generate_completion",
            new_callable=AsyncMock,
            side_effect=LlmConnectionError("Cannot connect"),
        ):
            result = asyncio.run(
                generate_from_context("ranger programs", sample_chunks)
            )
            assert result is None

    def test_returns_none_on_empty_response(self, sample_chunks):
        with patch(
            "api.nlq.generator.generate_completion",
            new_callable=AsyncMock,
            return_value="",
        ):
            result = asyncio.run(
                generate_from_context("ranger programs", sample_chunks)
            )
            assert result is None

    def test_returns_none_on_whitespace_only_response(self, sample_chunks):
        with patch(
            "api.nlq.generator.generate_completion",
            new_callable=AsyncMock,
            return_value="   \n  ",
        ):
            result = asyncio.run(
                generate_from_context("ranger programs", sample_chunks)
            )
            assert result is None

    def test_passes_system_prompt_and_context(self, sample_chunks):
        mock_completion = AsyncMock(return_value="An answer.")
        with patch("api.nlq.generator.generate_completion", mock_completion):
            asyncio.run(generate_from_context("ranger programs", sample_chunks))

            call_args = mock_completion.call_args[0][0]
            assert len(call_args) == 2
            assert call_args[0]["role"] == "system"
            assert "ONLY" in call_args[0]["content"]
            assert call_args[1]["role"] == "user"
            assert "ranger programs" in call_args[1]["content"]
            assert "Junior Ranger Program" in call_args[1]["content"]

    def test_context_includes_all_chunks(self, sample_chunks):
        mock_completion = AsyncMock(return_value="An answer.")
        with patch("api.nlq.generator.generate_completion", mock_completion):
            asyncio.run(generate_from_context("ranger programs", sample_chunks))

            user_message = mock_completion.call_args[0][0][1]["content"]
            assert "Yosemite National Park" in user_message
            assert "Grand Canyon National Park" in user_message

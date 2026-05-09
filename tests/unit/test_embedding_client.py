"""Unit tests for the embedding client."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from utils.embedding_client import get_embeddings, get_embeddings_sync
from utils.exceptions import LlmConnectionError


class TestGetEmbeddings:
    """Tests for async get_embeddings."""

    def test_successful_embedding(self):
        mock_embeddings = [[0.1] * 768]
        mock_response = MagicMock()
        mock_response.json.return_value = {"embeddings": mock_embeddings}
        mock_response.raise_for_status.return_value = None

        with patch("utils.embedding_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = asyncio.run(get_embeddings(["test text"]))

        assert len(result) == 1
        assert len(result[0]) == 768

    def test_batch_embedding(self):
        mock_embeddings = [[0.1] * 768, [0.2] * 768]
        mock_response = MagicMock()
        mock_response.json.return_value = {"embeddings": mock_embeddings}
        mock_response.raise_for_status.return_value = None

        with patch("utils.embedding_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = asyncio.run(get_embeddings(["text one", "text two"]))

        assert len(result) == 2

    def test_empty_input_returns_empty(self):
        result = asyncio.run(get_embeddings([]))
        assert result == []

    def test_connection_error_raises(self):
        with patch("utils.embedding_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.ConnectError("Connection refused")
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            with pytest.raises(LlmConnectionError, match="Cannot connect"):
                asyncio.run(get_embeddings(["test"]))

    def test_timeout_raises(self):
        with patch("utils.embedding_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.ReadTimeout("Timeout")
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            with pytest.raises(LlmConnectionError, match="timed out"):
                asyncio.run(get_embeddings(["test"]))


class TestGetEmbeddingsSync:
    """Tests for sync get_embeddings_sync."""

    def test_successful_embedding(self):
        mock_embeddings = [[0.1] * 768]
        mock_response = MagicMock()
        mock_response.json.return_value = {"embeddings": mock_embeddings}
        mock_response.raise_for_status.return_value = None

        with patch("utils.embedding_client.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value.__enter__.return_value = mock_client

            result = get_embeddings_sync(["test text"])

        assert len(result) == 1
        assert len(result[0]) == 768

    def test_batch_embedding(self):
        mock_embeddings = [[0.1] * 768, [0.2] * 768]
        mock_response = MagicMock()
        mock_response.json.return_value = {"embeddings": mock_embeddings}
        mock_response.raise_for_status.return_value = None

        with patch("utils.embedding_client.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value.__enter__.return_value = mock_client

            result = get_embeddings_sync(["text one", "text two"])

        assert len(result) == 2

    def test_empty_input_returns_empty(self):
        result = get_embeddings_sync([])
        assert result == []

    def test_connection_error_raises(self):
        with patch("utils.embedding_client.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.post.side_effect = httpx.ConnectError("Connection refused")
            mock_client_cls.return_value.__enter__.return_value = mock_client

            with pytest.raises(LlmConnectionError, match="Cannot connect"):
                get_embeddings_sync(["test"])

    def test_timeout_raises(self):
        with patch("utils.embedding_client.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.post.side_effect = httpx.ReadTimeout("Timeout")
            mock_client_cls.return_value.__enter__.return_value = mock_client

            with pytest.raises(LlmConnectionError, match="timed out"):
                get_embeddings_sync(["test"])

"""Ollama embedding API client.

Provides both async and sync interfaces for generating embeddings via
Ollama's /api/embed endpoint using the nomic-embed-text model.

Shared by both the API layer (api/main.py) and the pipeline layer
(scripts/processors/embedding_indexer.py), following the same pattern
as utils/logging.py and utils/exceptions.py.
"""

from __future__ import annotations

import httpx

from config.settings import config
from utils.exceptions import LlmConnectionError


async def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a list of texts (async).

    Calls Ollama's /api/embed endpoint which accepts a list of inputs
    and returns a list of embedding vectors.

    Args:
        texts: List of text strings to embed.

    Returns:
        List of embedding vectors (each a list of floats).

    Raises:
        LlmConnectionError: If Ollama is unreachable or returns an error.
    """
    if not texts:
        return []

    url = f"{config.OLLAMA_BASE_URL}/api/embed"
    payload = {
        "model": config.OLLAMA_EMBEDDING_MODEL,
        "input": texts,
    }

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(config.OLLAMA_TIMEOUT)
        ) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()
            embeddings: list[list[float]] = result.get("embeddings", [])
            return embeddings
    except httpx.ConnectError as e:
        raise LlmConnectionError(
            f"Cannot connect to Ollama at {config.OLLAMA_BASE_URL}. "
            "Is Ollama running? Start it with: ollama serve",
            context={"url": url},
        ) from e
    except httpx.TimeoutException as e:
        raise LlmConnectionError(
            f"Ollama embedding request timed out after {config.OLLAMA_TIMEOUT}s.",
            context={"url": url, "timeout": config.OLLAMA_TIMEOUT},
        ) from e
    except httpx.HTTPStatusError as e:
        raise LlmConnectionError(
            f"Ollama returned HTTP {e.response.status_code}: {e.response.text}",
            context={"url": url, "status_code": e.response.status_code},
        ) from e


def get_embeddings_sync(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a list of texts (synchronous).

    Synchronous version for use in collector scripts that aren't async.

    Args:
        texts: List of text strings to embed.

    Returns:
        List of embedding vectors (each a list of floats).

    Raises:
        LlmConnectionError: If Ollama is unreachable or returns an error.
    """
    if not texts:
        return []

    url = f"{config.OLLAMA_BASE_URL}/api/embed"
    payload = {
        "model": config.OLLAMA_EMBEDDING_MODEL,
        "input": texts,
    }

    try:
        with httpx.Client(timeout=httpx.Timeout(config.OLLAMA_TIMEOUT)) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()
            embeddings: list[list[float]] = result.get("embeddings", [])
            return embeddings
    except httpx.ConnectError as e:
        raise LlmConnectionError(
            f"Cannot connect to Ollama at {config.OLLAMA_BASE_URL}. "
            "Is Ollama running? Start it with: ollama serve",
            context={"url": url},
        ) from e
    except httpx.TimeoutException as e:
        raise LlmConnectionError(
            f"Ollama embedding request timed out after {config.OLLAMA_TIMEOUT}s.",
            context={"url": url, "timeout": config.OLLAMA_TIMEOUT},
        ) from e
    except httpx.HTTPStatusError as e:
        raise LlmConnectionError(
            f"Ollama returned HTTP {e.response.status_code}: {e.response.text}",
            context={"url": url, "status_code": e.response.status_code},
        ) from e

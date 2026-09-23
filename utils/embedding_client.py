"""Ollama embedding API client.

Provides both async and sync interfaces for checking Ollama availability
and generating embeddings via Ollama's HTTP API using the
``nomic-embed-text`` model.

Shared by both the API layer (api/main.py) and the pipeline layer
(scripts/processors/embedding_indexer.py), following the same pattern
as utils/logging.py and utils/exceptions.py.
"""

from __future__ import annotations

import httpx

from config.settings import config
from utils.exceptions import LlmConnectionError


def check_ollama_available() -> None:
    """Verify that the configured Ollama server is reachable.

    Raises:
        LlmConnectionError: If Ollama is unreachable or returns an error.
    """
    url = f"{config.OLLAMA_BASE_URL}/api/tags"

    try:
        with httpx.Client(timeout=httpx.Timeout(config.OLLAMA_TIMEOUT)) as client:
            response = client.get(url)
            response.raise_for_status()
    except httpx.ConnectError as e:
        raise LlmConnectionError(
            f"Cannot connect to Ollama at {config.OLLAMA_BASE_URL}. "
            "Is Ollama running? Start it with: ollama serve",
            context={"url": url},
        ) from e
    except httpx.TimeoutException as e:
        raise LlmConnectionError(
            f"Ollama availability check timed out after {config.OLLAMA_TIMEOUT}s.",
            context={"url": url, "timeout": config.OLLAMA_TIMEOUT},
        ) from e
    except httpx.HTTPStatusError as e:
        raise LlmConnectionError(
            f"Ollama returned HTTP {e.response.status_code}: {e.response.text}",
            context={"url": url, "status_code": e.response.status_code},
        ) from e


def check_embedding_model_available() -> None:
    """Verify that Ollama is reachable and has the embedding model installed.

    Raises:
        LlmConnectionError: If Ollama is unreachable, returns an error, or the
            configured embedding model has not been pulled.
    """
    url = f"{config.OLLAMA_BASE_URL}/api/tags"

    try:
        with httpx.Client(timeout=httpx.Timeout(config.OLLAMA_TIMEOUT)) as client:
            response = client.get(url)
            response.raise_for_status()
            models = response.json().get("models", [])
    except httpx.ConnectError as e:
        raise LlmConnectionError(
            f"Cannot connect to Ollama at {config.OLLAMA_BASE_URL}. "
            "Is Ollama running? Start it with: ollama serve",
            context={"url": url},
        ) from e
    except httpx.TimeoutException as e:
        raise LlmConnectionError(
            f"Ollama availability check timed out after {config.OLLAMA_TIMEOUT}s.",
            context={"url": url, "timeout": config.OLLAMA_TIMEOUT},
        ) from e
    except httpx.HTTPStatusError as e:
        raise LlmConnectionError(
            f"Ollama returned HTTP {e.response.status_code}: {e.response.text}",
            context={"url": url, "status_code": e.response.status_code},
        ) from e

    installed_models = {model.get("name") for model in models if model.get("name")}
    requested_model = config.OLLAMA_EMBEDDING_MODEL
    accepted_names = {requested_model}
    if ":" not in requested_model:
        accepted_names.add(f"{requested_model}:latest")

    if not installed_models.intersection(accepted_names):
        raise LlmConnectionError(
            f"Ollama embedding model '{requested_model}' is not installed. "
            f"Install it with: ollama pull {requested_model}",
            context={
                "url": url,
                "embedding_model": requested_model,
                "installed_models": sorted(installed_models),
            },
        )


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

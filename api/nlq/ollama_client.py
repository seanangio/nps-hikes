"""HTTP client for communicating with the Ollama REST API.

Uses httpx for async HTTP calls to Ollama's /api/chat endpoint
with tool-calling support.
"""

from __future__ import annotations

from typing import Any

import httpx

from config.settings import config
from utils.exceptions import LlmConnectionError


async def call_ollama(
    messages: list[dict[str, str]], tools: list[dict[str, Any]]
) -> dict[str, Any]:
    """Send a chat request to Ollama and return the response.

    Args:
        messages: Chat messages in Ollama format (role + content).
        tools: Tool definitions in OpenAI-compatible format.

    Returns:
        The full JSON response from Ollama.

    Raises:
        LlmConnectionError: If Ollama is unreachable or times out.
    """
    url = f"{config.OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": config.OLLAMA_MODEL,
        "messages": messages,
        "tools": tools,
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(config.OLLAMA_TIMEOUT)
        ) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result
    except httpx.ConnectError as e:
        raise LlmConnectionError(
            f"Cannot connect to Ollama at {config.OLLAMA_BASE_URL}. "
            "Is Ollama running? Start it with: ollama serve",
            context={"url": url},
        ) from e
    except httpx.TimeoutException as e:
        raise LlmConnectionError(
            f"Ollama request timed out after {config.OLLAMA_TIMEOUT}s. "
            "The model may still be loading.",
            context={"url": url, "timeout": config.OLLAMA_TIMEOUT},
        ) from e
    except httpx.HTTPStatusError as e:
        raise LlmConnectionError(
            f"Ollama returned HTTP {e.response.status_code}: {e.response.text}",
            context={"url": url, "status_code": e.response.status_code},
        ) from e


async def check_ollama_health() -> bool:
    """Check if Ollama is running and reachable.

    Returns:
        True if Ollama responds, False otherwise.
    """
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
            response = await client.get(f"{config.OLLAMA_BASE_URL}/api/tags")
            return response.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException):
        return False

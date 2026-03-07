"""
Custom exception hierarchy for the NPS Hikes project.

Provides specific exception classes for different failure modes across the
data collection pipeline, enabling targeted error handling and testable
error paths.

Hierarchy:
    NpsHikesError
    ├── ConfigurationError
    ├── CollectorError
    │   ├── ApiRequestError
    │   ├── ApiResponseError
    │   └── SchemaValidationError
    ├── DatabaseError
    │   ├── DatabaseConnectionError
    │   └── DatabaseWriteError
    ├── DataProcessingError
    └── LlmError
        ├── LlmConnectionError
        └── LlmResponseError
"""

from __future__ import annotations

from typing import Any


class NpsHikesError(Exception):
    """Base exception for all NPS Hikes project errors.

    Args:
        message: Human-readable error description.
        context: Optional dict of structured metadata for debugging
                 (e.g. park_code, table_name, endpoint).
    """

    def __init__(self, message: str, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.context: dict[str, Any] = context or {}


# --- Configuration errors ---


class ConfigurationError(NpsHikesError):
    """Missing or invalid configuration (API keys, DB credentials, settings)."""


# --- Data collection errors ---


class CollectorError(NpsHikesError):
    """Base exception for data collection failures."""


class ApiRequestError(CollectorError):
    """HTTP or network failure when calling an external API."""


class ApiResponseError(CollectorError):
    """Unexpected or invalid response from an external API."""


class SchemaValidationError(CollectorError):
    """Pydantic or Pandera schema validation failure."""


# --- Database errors ---


class DatabaseError(NpsHikesError):
    """Base exception for database operation failures."""


class DatabaseConnectionError(DatabaseError):
    """Unable to connect to the database."""


class DatabaseWriteError(DatabaseError):
    """Failed to write, upsert, append, or truncate database records."""


# --- Processing errors ---


class DataProcessingError(NpsHikesError):
    """Failure during data transformation or processing steps."""


# --- LLM errors ---


class LlmError(NpsHikesError):
    """Base exception for LLM-related failures."""


class LlmConnectionError(LlmError):
    """Unable to connect to Ollama or LLM service."""


class LlmResponseError(LlmError):
    """LLM returned an unparseable or invalid response."""

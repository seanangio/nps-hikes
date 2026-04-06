"""
HTTP client wrapper for the NPS Hikes FastAPI backend.

Provides functions to fetch parks, trails, hiked points, and stats from the API.
All responses are returned as dictionaries matching the API's JSON structure.
"""

import os
from typing import Any

import requests
import streamlit as st

# Configure API base URL from environment variable
API_BASE_URL = os.getenv("NPS_API_URL", "http://localhost:8001")


class APIError(Exception):
    """Exception raised when API requests fail."""

    pass


@st.cache_data(ttl=300)  # Cache for 5 minutes
def fetch_parks(
    park_code: str | None = None,
    state: str | None = None,
    visited: bool | None = None,
    boundary: bool = False,
) -> dict[str, Any]:
    """
    Fetch parks from the API.

    Args:
        park_code: Optional 4-character park code filter
        state: Optional 2-letter state code filter
        visited: Optional visited status filter
        boundary: Include simplified boundary GeoJSON

    Returns:
        API response dict with keys: park_count, visited_count, parks

    Raises:
        APIError: If the API request fails
    """
    url = f"{API_BASE_URL}/parks"
    params = {}

    if park_code:
        params["park_code"] = park_code
    if state:
        params["state"] = state
    if visited is not None:
        params["visited"] = visited
    if boundary:
        params["boundary"] = boundary

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise APIError(f"Failed to fetch parks: {e!s}") from e


@st.cache_data(ttl=60)  # Cache for 1 minute (trails change more frequently)
def fetch_trails(
    park_code: str | None = None,
    state: str | None = None,
    hiked: bool | None = None,
    min_length: float | None = None,
    max_length: float | None = None,
    source: str | None = None,
    viz_3d: bool | None = None,
    geojson: bool = False,
    limit: int = 1000,
) -> dict[str, Any]:
    """
    Fetch trails from the API.

    Args:
        park_code: Optional 4-character park code filter
        state: Optional 2-letter state code filter
        hiked: Optional hiked status filter
        min_length: Optional minimum trail length in miles
        max_length: Optional maximum trail length in miles
        source: Optional data source filter ('TNM' or 'OSM')
        viz_3d: Optional 3D visualization availability filter
        geojson: Include trail geometry GeoJSON
        limit: Maximum number of trails to return

    Returns:
        API response dict with keys: trail_count, total_miles, trails, pagination

    Raises:
        APIError: If the API request fails
    """
    url = f"{API_BASE_URL}/trails"
    params = {"limit": limit}

    if park_code:
        params["park_code"] = park_code
    if state:
        params["state"] = state
    if hiked is not None:
        params["hiked"] = hiked
    if min_length is not None:
        params["min_length"] = min_length
    if max_length is not None:
        params["max_length"] = max_length
    if source:
        params["source"] = source
    if viz_3d is not None:
        params["viz_3d"] = viz_3d
    if geojson:
        params["geojson"] = geojson

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise APIError(f"Failed to fetch trails: {e!s}") from e


@st.cache_data(ttl=300)  # Cache for 5 minutes
def fetch_hiked_points(park_code: str | None = None) -> dict[str, Any]:
    """
    Fetch hiked location points from the API.

    Args:
        park_code: Optional 4-character park code filter

    Returns:
        API response dict with keys: count, hiked_points

    Raises:
        APIError: If the API request fails
    """
    url = f"{API_BASE_URL}/trails/hiked-points"
    params = {}

    if park_code:
        params["park_code"] = park_code

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise APIError(f"Failed to fetch hiked points: {e!s}") from e


@st.cache_data(ttl=300)  # Cache for 5 minutes
def fetch_stats(hiked: bool | None = None) -> dict[str, Any]:
    """
    Fetch aggregate trail statistics from the API.

    Args:
        hiked: Optional hiked status filter

    Returns:
        API response dict with aggregate stats

    Raises:
        APIError: If the API request fails
    """
    url = f"{API_BASE_URL}/stats"
    params = {}

    if hiked is not None:
        params["hiked"] = hiked

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise APIError(f"Failed to fetch stats: {e!s}") from e


@st.cache_data(ttl=300)  # Cache for 5 minutes
def fetch_park_summary(park_code: str) -> dict[str, Any]:
    """
    Fetch detailed park summary from the API.

    Args:
        park_code: 4-character park code

    Returns:
        API response dict with park metadata and trail statistics

    Raises:
        APIError: If the API request fails
    """
    url = f"{API_BASE_URL}/parks/{park_code}/summary"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise APIError(f"Failed to fetch park summary: {e!s}") from e


def test_api_connection() -> bool:
    """
    Test if the API is reachable.

    Returns:
        True if API is healthy, False otherwise
    """
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False

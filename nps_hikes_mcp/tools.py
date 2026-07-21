"""MCP-facing tool wrappers around the existing structured query layer."""

from __future__ import annotations

import re
from typing import Any

from api.queries import fetch_all_parks, fetch_park_summary, fetch_stats, fetch_trails
from utils.exceptions import NpsHikesError


class McpToolError(Exception):
    """Base exception for MCP tool failures."""


class McpToolNotFoundError(McpToolError):
    """Raised when a requested entity does not exist."""


def _raise_operational_error(tool_name: str, exc: Exception) -> None:
    raise McpToolError(f"{tool_name} failed: {exc}") from exc


def _validate_park_code(park_code: str | None) -> None:
    if park_code is None:
        return
    if not re.fullmatch(r"^[a-z]{4}$", park_code):
        raise McpToolError("park_code must be a 4-letter lowercase code like 'yose'.")


def _validate_state(state: str | None) -> None:
    if state is None:
        return
    if not re.fullmatch(r"^[A-Z]{2}$", state):
        raise McpToolError("state must be a 2-letter uppercase code like 'CA' or 'UT'.")


def _validate_source(source: str | None) -> None:
    if source is None:
        return
    if source not in {"TNM", "OSM"}:
        raise McpToolError("source must be either 'TNM' or 'OSM'.")


def _validate_limit(limit: int) -> None:
    if not 1 <= limit <= 1000:
        raise McpToolError("limit must be between 1 and 1000.")


def _validate_length_range(
    min_length: float | None,
    max_length: float | None,
) -> None:
    if min_length is not None and min_length < 0:
        raise McpToolError("min_length must be non-negative.")
    if max_length is not None and max_length < 0:
        raise McpToolError("max_length must be non-negative.")
    if min_length is not None and max_length is not None and min_length > max_length:
        raise McpToolError("min_length cannot be greater than max_length.")


def _validate_visit_year(visit_year: int | None) -> None:
    if visit_year is None:
        return
    if not 2000 <= visit_year <= 2100:
        raise McpToolError("visit_year must be between 2000 and 2100.")


def _normalize_visit_month(visit_month: str | list[str] | None) -> list[str] | None:
    if visit_month is None:
        return None
    if isinstance(visit_month, str):
        return [visit_month]
    return visit_month


def _compact_trail(trail: dict[str, Any]) -> dict[str, Any]:
    return {
        "trail_id": trail["trail_id"],
        "trail_name": trail["trail_name"],
        "park_code": trail["park_code"],
        "park_name": trail["park_name"],
        "states": trail["states"],
        "source": trail["source"],
        "length_miles": trail["length_miles"],
        "hiked": trail["hiked"],
        "viz_3d_available": trail["viz_3d_available"],
        "viz_3d_slug": trail["viz_3d_slug"],
    }


def _compact_park(park: dict[str, Any]) -> dict[str, Any]:
    return {
        "park_code": park["park_code"],
        "park_name": park["park_name"],
        "full_name": park["full_name"],
        "states": park["states"],
        "visit_month": park["visit_month"],
        "visit_year": park["visit_year"],
        "url": park["url"],
    }


def _format_applied_filters(filters: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in filters.items() if value is not None}


def _summarize_trail_filters(filters: dict[str, Any]) -> str:
    parts = []
    if filters.get("park_code"):
        parts.append(f"park {filters['park_code']}")
    if filters.get("state"):
        parts.append(f"state {filters['state']}")
    if filters.get("hiked") is True:
        parts.append("hiked trails only")
    elif filters.get("hiked") is False:
        parts.append("unhiked trails only")
    if filters.get("source"):
        parts.append(f"source {filters['source']}")
    if filters.get("min_length") is not None:
        parts.append(f"min {filters['min_length']} mi")
    if filters.get("max_length") is not None:
        parts.append(f"max {filters['max_length']} mi")
    if filters.get("viz_3d") is True:
        parts.append("3D viz only")
    elif filters.get("viz_3d") is False:
        parts.append("no 3D viz")
    return ", ".join(parts)


def search_trails(
    park_code: str | None = None,
    state: str | None = None,
    hiked: bool | None = None,
    min_length: float | None = None,
    max_length: float | None = None,
    source: str | None = None,
    viz_3d: bool | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Search trails using the existing structured query logic."""
    _validate_park_code(park_code)
    _validate_state(state)
    _validate_source(source)
    _validate_limit(limit)
    _validate_length_range(min_length, max_length)

    filters = {
        "park_code": park_code,
        "state": state,
        "hiked": hiked,
        "min_length": min_length,
        "max_length": max_length,
        "source": source,
        "viz_3d": viz_3d,
        "limit": limit,
    }
    try:
        result = fetch_trails(
            park_code=park_code,
            state=state,
            hiked=hiked,
            min_length=min_length,
            max_length=max_length,
            source=source,
            viz_3d=viz_3d,
            limit=limit,
            offset=0,
            geojson=False,
        )
    except NpsHikesError as exc:
        _raise_operational_error("search_trails", exc)

    filter_summary = _summarize_trail_filters(filters)
    summary = (
        f"Found {result['trail_count']} trails totaling {result['total_miles']} miles"
    )
    if filter_summary:
        summary += f" matching {filter_summary}"
    summary += "."

    return {
        "summary": summary,
        "trail_count": result["trail_count"],
        "total_miles": result["total_miles"],
        "applied_filters": _format_applied_filters(filters),
        "trails": [_compact_trail(trail) for trail in result["trails"]],
    }


def search_parks(
    visited: bool | None = None,
    visit_year: int | None = None,
    visit_month: str | list[str] | None = None,
    park_code: str | None = None,
    state: str | None = None,
) -> dict[str, Any]:
    """Search parks using the existing structured query logic."""
    _validate_park_code(park_code)
    _validate_state(state)
    _validate_visit_year(visit_year)

    normalized_visit_month = _normalize_visit_month(visit_month)
    filters = {
        "visited": visited,
        "visit_year": visit_year,
        "visit_month": normalized_visit_month,
        "park_code": park_code,
        "state": state,
    }
    try:
        result = fetch_all_parks(
            visited=visited,
            visit_year=visit_year,
            visit_month=normalized_visit_month,
            park_code=park_code,
            state=state,
            description=False,
            boundary=False,
        )
    except NpsHikesError as exc:
        _raise_operational_error("search_parks", exc)

    summary = f"Found {result['park_count']} parks, including {result['visited_count']} visited parks."

    return {
        "summary": summary,
        "park_count": result["park_count"],
        "visited_count": result["visited_count"],
        "applied_filters": _format_applied_filters(filters),
        "parks": [_compact_park(park) for park in result["parks"]],
    }


def search_stats(hiked: bool | None = None) -> dict[str, Any]:
    """Return aggregate trail statistics."""
    if hiked is not None and not isinstance(hiked, bool):
        raise McpToolError("hiked must be a boolean value.")

    try:
        result = fetch_stats(hiked=hiked)
    except NpsHikesError as exc:
        _raise_operational_error("search_stats", exc)
    scope = "all trails"
    if hiked is True:
        scope = "hiked trails"
    elif hiked is False:
        scope = "unhiked trails"

    summary = (
        f"{scope.capitalize()} include {result['total_trails']} trails across "
        f"{result['parks_count']} parks and {result['states_count']} states, totaling "
        f"{result['total_miles']} miles."
    )

    return {
        "summary": summary,
        "applied_filters": _format_applied_filters({"hiked": hiked}),
        **result,
    }


def search_park_summary(park_code: str) -> dict[str, Any]:
    """Return a park overview with MCP-friendly grouping."""
    _validate_park_code(park_code)
    try:
        result = fetch_park_summary(park_code=park_code)
    except NpsHikesError as exc:
        _raise_operational_error("search_park_summary", exc)
    if result is None:
        raise McpToolNotFoundError(f"Park not found for park_code={park_code}")

    summary = (
        f"{result['park_name']} has {result['total_trails']} trails totaling "
        f"{result['total_miles']} miles; {result['hiked_trails']} of those trails "
        f"have been hiked."
    )

    return {
        "summary": summary,
        "park": {
            "park_code": result["park_code"],
            "park_name": result["park_name"],
            "full_name": result["full_name"],
            "designation": result["designation"],
            "states": result["states"],
            "latitude": result["latitude"],
            "longitude": result["longitude"],
            "url": result["url"],
        },
        "trail_stats": {
            "total_trails": result["total_trails"],
            "total_miles": result["total_miles"],
            "avg_trail_length": result["avg_trail_length"],
            "hiked_trails": result["hiked_trails"],
            "hiked_miles": result["hiked_miles"],
            "viz_3d_count": result["viz_3d_count"],
        },
        "source_breakdown": result["source_breakdown"],
        "visit_info": {
            "visit_month": result["visit_month"],
            "visit_year": result["visit_year"],
            "visited": result["visit_year"] is not None,
        },
    }


TOOL_DEFINITIONS = [
    {
        "name": "search_trails",
        "description": "Retrieve trails using explicit structured filters.",
        "input_schema": {
            "type": "object",
            "properties": {
                "park_code": {"type": "string", "pattern": "^[a-z]{4}$"},
                "state": {"type": "string", "pattern": "^[A-Z]{2}$"},
                "hiked": {"type": "boolean"},
                "min_length": {"type": "number"},
                "max_length": {"type": "number"},
                "source": {"type": "string", "enum": ["TNM", "OSM"]},
                "viz_3d": {"type": "boolean"},
                "limit": {
                    "type": "integer",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 1000,
                },
            },
        },
    },
    {
        "name": "search_parks",
        "description": "Retrieve parks using visit and metadata filters.",
        "input_schema": {
            "type": "object",
            "properties": {
                "visited": {"type": "boolean"},
                "visit_year": {"type": "integer", "minimum": 2000, "maximum": 2100},
                "visit_month": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ]
                },
                "park_code": {"type": "string", "pattern": "^[a-z]{4}$"},
                "state": {"type": "string", "pattern": "^[A-Z]{2}$"},
            },
        },
    },
    {
        "name": "search_stats",
        "description": "Return aggregate trail statistics.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hiked": {"type": "boolean"},
            },
        },
    },
    {
        "name": "search_park_summary",
        "description": "Return a detailed overview for a specific park.",
        "input_schema": {
            "type": "object",
            "properties": {
                "park_code": {"type": "string", "pattern": "^[a-z]{4}$"},
            },
            "required": ["park_code"],
        },
    },
]

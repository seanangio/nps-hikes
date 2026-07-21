"""Resource content for the local nps-hikes MCP server."""

from __future__ import annotations

from typing import Any

from api.nlq.park_lookup import get_park_lookup


def get_dataset_overview() -> str:
    """Return stable background context about the local dataset."""
    return """# NPS Hikes Dataset Overview

`nps-hikes` is a local-first project for exploring U.S. National Park trail data.

Available data domains:
- National Park metadata such as names, park codes, states, coordinates, URLs, and visit dates.
- Deduplicated trail data collected from The National Map (TNM) and OpenStreetMap (OSM).
- Personal hiking status based on matched Google My Maps hiking locations.
- Park- and trail-level aggregate statistics derived from the local Postgres database.

Important constraints:
- This MCP server is designed for a single local user and reads from the user's local project database.
- Tool outputs are deterministic and structured; the MCP server does not generate final prose answers.
- v1 focuses on structured parks, trails, stats, and park summary queries.
- Topic/semantic search is intentionally out of scope for the v1 MCP surface.
"""


def get_search_methodology() -> str:
    """Explain result provenance and interpretation."""
    return """# Search Methodology

Trail provenance:
- `TNM` means The National Map / USGS trail data.
- `OSM` means OpenStreetMap trail data.

Deduplication:
- Trails are combined across TNM and OSM.
- When a TNM and OSM trail in the same park have highly similar names, the TNM record is kept and the overlapping OSM record is excluded.

Status fields:
- `visited` applies to parks and comes from the local park visit log.
- `hiked` applies to trails and is inferred from locally matched Google My Maps hiking locations.

Interpretation notes:
- Empty results mean the query succeeded but nothing matched the requested filters.
- Tool summaries are compact helper text for the host assistant, not final natural-language answers.
- Results reflect the freshness and completeness of the user's local dataset, not live web data.
"""


def get_park_lookup_resource() -> dict[str, Any]:
    """Return a structured park name to park_code lookup resource."""
    lookup = get_park_lookup()

    parks_by_code: dict[str, dict[str, Any]] = {}
    for name, code in lookup.items():
        if code == name:
            parks_by_code.setdefault(
                code,
                {
                    "park_code": code,
                    "names": [],
                },
            )
            continue

        park = parks_by_code.setdefault(
            code,
            {
                "park_code": code,
                "names": [],
            },
        )
        if name not in park["names"]:
            park["names"].append(name)

    parks = []
    for code in sorted(parks_by_code):
        park = parks_by_code[code]
        park["names"].sort(key=len, reverse=True)
        park["primary_name"] = park["names"][0] if park["names"] else code
        parks.append(park)

    return {
        "park_count": len(parks),
        "parks": parks,
    }


RESOURCE_DEFINITIONS = [
    {
        "uri": "dataset_overview",
        "name": "dataset_overview",
        "description": "Project and dataset overview for the local nps-hikes MCP server.",
        "mime_type": "text/markdown",
    },
    {
        "uri": "park_lookup",
        "name": "park_lookup",
        "description": "Structured mapping of park names to canonical 4-letter park codes.",
        "mime_type": "application/json",
    },
    {
        "uri": "search_methodology",
        "name": "search_methodology",
        "description": "Data provenance, deduplication, and status-field interpretation notes.",
        "mime_type": "text/markdown",
    },
]


def read_resource(uri: str) -> str | dict[str, Any]:
    """Return resource content for a known resource URI."""
    if uri == "dataset_overview":
        return get_dataset_overview()
    if uri == "park_lookup":
        return get_park_lookup_resource()
    if uri == "search_methodology":
        return get_search_methodology()
    raise KeyError(f"Unknown resource URI: {uri}")

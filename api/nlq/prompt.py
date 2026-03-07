"""Prompt building and tool definitions for natural language queries.

Defines the tool schemas (OpenAI-compatible format) that tell the LLM
which functions it can call, and builds the system message with the
park name lookup table injected.
"""

from __future__ import annotations

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_trails",
            "description": (
                "Search for hiking trails in National Parks. "
                "Use this for any question about trails, hikes, or trail-related queries."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "park_code": {
                        "type": "string",
                        "description": (
                            "4-character lowercase park code. "
                            "Use the park lookup table to find the correct code."
                        ),
                    },
                    "state": {
                        "type": "string",
                        "description": "2-letter uppercase US state code (e.g., 'CA', 'UT')",
                    },
                    "source": {
                        "type": "string",
                        "enum": ["TNM", "OSM"],
                        "description": "Data source: TNM (USGS) or OSM (OpenStreetMap)",
                    },
                    "hiked": {
                        "type": "boolean",
                        "description": "true = only trails the user has hiked, false = only unhibited trails",
                    },
                    "min_length": {
                        "type": "number",
                        "description": "Minimum trail length in miles",
                    },
                    "max_length": {
                        "type": "number",
                        "description": "Maximum trail length in miles",
                    },
                    "trail_type": {
                        "type": "string",
                        "enum": ["path", "footway", "track", "steps", "cycleway"],
                        "description": "OSM highway type filter",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (1-1000, default 50)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_parks",
            "description": (
                "Search for National Parks. "
                "Use this for questions about parks, which parks exist, or park visit status."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "visited": {
                        "type": "boolean",
                        "description": (
                            "true = only visited parks, false = only unvisited parks. "
                            "Omit to return all parks."
                        ),
                    },
                },
                "required": [],
            },
        },
    },
]

_SYSTEM_MESSAGE_TEMPLATE = """\
You are a trail finder assistant for US National Parks.
Your ONLY job is to call the appropriate function with the correct parameters \
based on the user's question. Always respond with a function call, never with plain text.

Park name to park_code lookup:
{park_lookup_text}

Rules:
- Always use the park_code (4 lowercase letters), never the full park name, as the parameter value.
- State codes must be 2 uppercase letters (e.g., CA, UT, CO).
- Trail lengths are in miles.
- For "short" trails, use max_length=3. For "long" trails, use min_length=5.
- If the user asks about parks (not trails), use search_parks.
- If the user asks about trails or hikes, use search_trails.
- Only include parameters that the user's question implies. Do not add extra filters.\
"""


def build_system_message(park_lookup_text: str) -> str:
    """Build the system message with the park lookup table injected.

    Args:
        park_lookup_text: The formatted park name → code text from
            park_lookup.build_park_lookup_text().

    Returns:
        The complete system message string.
    """
    return _SYSTEM_MESSAGE_TEMPLATE.format(park_lookup_text=park_lookup_text)


def build_chat_messages(query: str, system_message: str) -> list[dict]:
    """Build the message list for the Ollama /api/chat request.

    Args:
        query: The user's natural language question.
        system_message: The system message from build_system_message().

    Returns:
        A list of message dicts in the Ollama chat format.
    """
    return [
        {"role": "system", "content": system_message},
        {"role": "user", "content": query},
    ]

"""Parse and validate LLM responses into structured API parameters.

Extracts tool calls from Ollama responses, normalizes parameter values,
and validates them against expected types and ranges.
"""

from __future__ import annotations

import json
import re
from typing import Any

from api.nlq.park_lookup import resolve_park_code
from utils.exceptions import LlmResponseError

# US state name -> 2-letter code mapping for normalization
_STATE_NAME_TO_CODE: dict[str, str] = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
}

VALID_FUNCTIONS = {"search_trails", "search_parks"}


def parse_tool_call(response: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Extract function name and arguments from an Ollama chat response.

    Tries two strategies:
    1. Standard tool_calls format from Ollama's chat API.
    2. JSON block in the message content (fallback for models that
       respond with JSON text instead of structured tool calls).

    Args:
        response: The raw JSON response from Ollama /api/chat.

    Returns:
        A tuple of (function_name, arguments_dict).

    Raises:
        LlmResponseError: If no tool call can be extracted.
    """
    message = response.get("message", {})

    # Strategy 1: Standard tool_calls format
    tool_calls = message.get("tool_calls")
    if tool_calls and isinstance(tool_calls, list):
        call = tool_calls[0]
        function = call.get("function", {})
        name = function.get("name", "")
        args = function.get("arguments", {})
        if name:
            return name, args if isinstance(args, dict) else {}

    # Strategy 2: JSON in message content
    content = message.get("content", "")
    if content:
        extracted = _extract_json_from_text(content)
        if extracted:
            name = extracted.get("function", extracted.get("name", ""))
            args = extracted.get(
                "arguments", extracted.get("args", extracted.get("parameters", {}))
            )
            if name:
                return name, args if isinstance(args, dict) else {}

    raise LlmResponseError(
        "Could not extract a function call from the LLM response. "
        "Try rephrasing your question.",
        context={"response_content": content[:500] if content else "empty"},
    )


def _extract_json_from_text(text: str) -> dict[str, Any] | None:
    """Try to extract a JSON object from free text.

    Looks for JSON blocks (with or without markdown fences),
    then tries to find balanced braces in the text.
    """
    # Try to find JSON in markdown code blocks
    code_block = re.search(r"```(?:json)?\s*(\{.+\})\s*```", text, re.DOTALL)
    if code_block:
        try:
            result: dict[str, Any] = json.loads(code_block.group(1))
            return result
        except json.JSONDecodeError:
            pass

    # Try to find a JSON object by locating balanced braces
    start = text.find("{")
    if start == -1:
        return None

    # Walk forward to find the matching closing brace
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    parsed: dict[str, Any] = json.loads(text[start : i + 1])
                    return parsed
                except json.JSONDecodeError:
                    return None

    return None


def validate_and_normalize(
    function_name: str,
    params: dict[str, Any],
    park_lookup: dict[str, str],
) -> tuple[str, dict[str, Any]]:
    """Validate and normalize extracted parameters.

    Auto-corrects common LLM mistakes:
    - Uppercase park codes → lowercase
    - Full state names → 2-letter codes
    - Park names in park_code → resolved to actual codes
    - Out-of-range values clamped

    Args:
        function_name: The extracted function name.
        params: The raw parameters from the LLM.
        park_lookup: The park name → code lookup dict.

    Returns:
        A tuple of (validated_function_name, cleaned_params).

    Raises:
        LlmResponseError: If the function name is not recognized.
    """
    if function_name not in VALID_FUNCTIONS:
        raise LlmResponseError(
            f"Unknown function '{function_name}'. "
            f"Expected one of: {', '.join(sorted(VALID_FUNCTIONS))}",
            context={"function_name": function_name},
        )

    if function_name == "search_trails":
        return function_name, _normalize_trail_params(params, park_lookup)
    else:
        return function_name, _normalize_park_params(params)


def _normalize_trail_params(
    params: dict[str, Any], park_lookup: dict[str, str]
) -> dict[str, Any]:
    """Normalize parameters for the search_trails function."""
    cleaned: dict[str, Any] = {}

    # Park code: resolve names, lowercase
    if params.get("park_code"):
        raw = str(params["park_code"])
        resolved = resolve_park_code(raw, park_lookup)
        if resolved:
            cleaned["park_code"] = resolved

    # State: convert names to codes, uppercase
    if params.get("state"):
        raw = str(params["state"]).strip()
        state_code = _STATE_NAME_TO_CODE.get(raw.lower())
        if state_code:
            cleaned["state"] = state_code
        elif re.match(r"^[A-Za-z]{2}$", raw):
            cleaned["state"] = raw.upper()

    # Source: uppercase
    if params.get("source"):
        raw = str(params["source"]).upper()
        if raw in ("TNM", "OSM"):
            cleaned["source"] = raw

    # Hiked: coerce to bool
    if "hiked" in params and params["hiked"] is not None:
        cleaned["hiked"] = bool(params["hiked"])

    # Length filters: clamp to valid range
    for key in ("min_length", "max_length"):
        if key in params and params[key] is not None:
            try:
                val = float(params[key])
                cleaned[key] = max(0.0, min(val, 100.0))
            except (ValueError, TypeError):
                pass

    # Trail type
    if params.get("trail_type"):
        raw = str(params["trail_type"]).lower()
        if raw in ("path", "footway", "track", "steps", "cycleway"):
            cleaned["trail_type"] = raw

    # Limit: clamp to valid range
    if "limit" in params and params["limit"] is not None:
        try:
            val = int(params["limit"])
            cleaned["limit"] = max(1, min(val, 1000))
        except (ValueError, TypeError):
            pass

    return cleaned


def _normalize_park_params(params: dict[str, Any]) -> dict[str, Any]:
    """Normalize parameters for the search_parks function."""
    cleaned: dict[str, Any] = {}

    if "visited" in params and params["visited"] is not None:
        cleaned["visited"] = bool(params["visited"])

    return cleaned

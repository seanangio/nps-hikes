"""Parse and validate LLM responses into structured API parameters.

Extracts tool calls from Ollama responses, normalizes parameter values,
and validates them against expected types and ranges.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from api.nlq.park_lookup import resolve_park_code
from utils.exceptions import LlmResponseError

logger = logging.getLogger(__name__)

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

# Month name → DB-compatible values for SQL IN clauses.
# The DB stores a mix of 3-letter ("Oct") and full ("October") formats,
# so both variants are included to match either.
_MONTH_NAME_TO_DB_VALUES: dict[str, list[str]] = {
    "january": ["Jan", "January"],
    "february": ["Feb", "February"],
    "march": ["Mar", "March"],
    "april": ["Apr", "April"],
    "may": ["May"],
    "june": ["Jun", "June"],
    "july": ["Jul", "July"],
    "august": ["Aug", "August"],
    "september": ["Sep", "September"],
    "october": ["Oct", "October"],
    "november": ["Nov", "November"],
    "december": ["Dec", "December"],
}

# 3-letter abbreviation → full lowercase month key
_MONTH_ABBR_TO_FULL: dict[str, str] = {
    "jan": "january",
    "feb": "february",
    "mar": "march",
    "apr": "april",
    "may": "may",
    "jun": "june",
    "jul": "july",
    "aug": "august",
    "sep": "september",
    "oct": "october",
    "nov": "november",
    "dec": "december",
}

# Numeric string → full lowercase month key
_MONTH_NUM_TO_FULL: dict[str, str] = {
    "1": "january",
    "2": "february",
    "3": "march",
    "4": "april",
    "5": "may",
    "6": "june",
    "7": "july",
    "8": "august",
    "9": "september",
    "10": "october",
    "11": "november",
    "12": "december",
}

# Season → list of month keys
_SEASON_TO_MONTHS: dict[str, list[str]] = {
    "spring": ["march", "april", "may"],
    "summer": ["june", "july", "august"],
    "fall": ["september", "october", "november"],
    "autumn": ["september", "october", "november"],
    "winter": ["december", "january", "february"],
}

VALID_FUNCTIONS = {
    "search_trails",
    "search_parks",
    "search_stats",
    "search_park_summary",
    "search_by_topic",
}


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


_NEGATION_PATTERN = re.compile(
    r"\b(haven'?t|hasn'?t|don'?t|didn'?t|not|never|unvisited|unhiked)\b",
    re.IGNORECASE,
)


def validate_and_normalize(
    function_name: str,
    params: dict[str, Any],
    park_lookup: dict[str, str],
    query: str = "",
) -> tuple[str, dict[str, Any]]:
    """Validate and normalize extracted parameters.

    Auto-corrects common LLM mistakes:
    - Uppercase park codes → lowercase
    - Full state names → 2-letter codes
    - Park names in park_code → resolved to actual codes
    - Out-of-range values clamped
    - Hallucinated parameters removed (search_by_topic only)
    - Negation in query with wrong boolean polarity

    Args:
        function_name: The extracted function name.
        params: The raw parameters from the LLM.
        park_lookup: The park name → code lookup dict.
        query: The original user query (used for negation detection).

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
        cleaned = _normalize_trail_params(params, park_lookup)
    elif function_name == "search_parks":
        cleaned = _normalize_park_params(params)
    elif function_name == "search_stats":
        cleaned = _normalize_stats_params(params)
    elif function_name == "search_by_topic":
        cleaned = _normalize_topic_search_params(params, park_lookup)
    else:
        cleaned = _normalize_park_summary_params(params, park_lookup)

    if query and function_name == "search_by_topic":
        cleaned = _validate_extracted_params(cleaned, query, park_lookup)

    if query:
        cleaned = _apply_negation_correction(query, function_name, cleaned)

    return function_name, cleaned


def _apply_negation_correction(
    query: str, function_name: str, params: dict[str, Any]
) -> dict[str, Any]:
    """Flip boolean params when the query contains negation but the LLM set True.

    Small LLMs often ignore negation words and set boolean parameters to True
    when the user meant False. This detects negation in the original query
    and corrects the mismatch.
    """
    if not _NEGATION_PATTERN.search(query):
        return params

    if function_name == "search_parks" and params.get("visited") is True:
        params["visited"] = False
    if (
        function_name in ("search_trails", "search_stats", "search_by_topic")
        and params.get("hiked") is True
    ):
        params["hiked"] = False

    return params


# Terms that indicate the user is referring to hiking/completion status.
_HIKED_TERMS = [
    "hiked",
    "completed",
    "finished",
    "done",
    "haven't",
    "haven't hiked",
    "not hiked",
    "never hiked",
    "to do",
    "want to hike",
    "planning to",
]

# Terms that indicate the user is referring to a data source.
_SOURCE_TERMS = ["tnm", "usgs", "osm", "openstreetmap"]

# Terms that indicate length intent direction.
_LONG_TERMS = ["long", "longer", "lengthy"]
_SHORT_TERMS = ["short", "shorter", "brief"]

# Terms that indicate trail length is mentioned.
_LENGTH_TERMS = (
    _LONG_TERMS
    + _SHORT_TERMS
    + [
        "miles",
        "mile",
        "under",
        "over",
        "less than",
        "more than",
        "at least",
        "longer than",
        "shorter than",
    ]
)


def _validate_extracted_params(
    params: dict[str, Any],
    query: str,
    park_lookup: dict[str, str],
) -> dict[str, Any]:
    """Remove hallucinated parameters not supported by the query text.

    Small LLMs often infer parameters from world knowledge (e.g., adding
    park_code="arch" when the user asks about "slot canyons") even though
    the user didn't mention a specific park. This function checks each
    extracted parameter against the original query and removes those
    without textual evidence.

    Only applies to search_by_topic parameters. The ``query`` field
    itself is never removed.

    Args:
        params: Normalized parameters from the LLM.
        query: The original user query string.
        park_lookup: The park name → code lookup dict.

    Returns:
        Cleaned parameters with unsupported values removed.
    """
    cleaned = params.copy()
    query_lower = query.lower()

    # --- park_code: remove if no park name mentioned in query ---
    if "park_code" in cleaned:
        park_name_mentioned = any(
            name in query_lower
            for name, code in park_lookup.items()
            # Skip 4-letter codes to avoid false positives on common words
            if name != code and len(name) > 4
        )
        if not park_name_mentioned:
            logger.info(
                "Removing unsupported park_code='%s' from query: %s",
                cleaned["park_code"],
                query,
            )
            del cleaned["park_code"]

    # --- source: remove if not mentioned ---
    if "source" in cleaned:
        source_mentioned = any(term in query_lower for term in _SOURCE_TERMS)
        if not source_mentioned:
            logger.info(
                "Removing unsupported source='%s' from query: %s",
                cleaned["source"],
                query,
            )
            del cleaned["source"]

    # --- hiked: remove if completion status not mentioned ---
    if "hiked" in cleaned:
        hiked_mentioned = any(term in query_lower for term in _HIKED_TERMS)
        if not hiked_mentioned:
            logger.info(
                "Removing unsupported hiked=%s from query: %s",
                cleaned["hiked"],
                query,
            )
            del cleaned["hiked"]

    # --- length filters: remove zero values (nonsensical) ---
    if cleaned.get("min_length") == 0 or cleaned.get("min_length") == 0.0:
        del cleaned["min_length"]
    if cleaned.get("max_length") == 0 or cleaned.get("max_length") == 0.0:
        del cleaned["max_length"]

    # --- length filters: remove if no length terms mentioned ---
    if "min_length" in cleaned or "max_length" in cleaned:
        length_mentioned = any(term in query_lower for term in _LENGTH_TERMS)
        if not length_mentioned:
            logger.info("Removing unsupported length filters from query: %s", query)
            cleaned.pop("min_length", None)
            cleaned.pop("max_length", None)

    # --- length direction: swap if "long" gave max_length instead of min ---
    if (
        "min_length" not in cleaned
        and "max_length" in cleaned
        and any(term in query_lower for term in _LONG_TERMS)
    ):
        logger.info(
            "Swapping max_length=%s to min_length for 'long' query: %s",
            cleaned["max_length"],
            query,
        )
        cleaned["min_length"] = cleaned.pop("max_length")

    return cleaned


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


def _normalize_visit_month(raw: str) -> list[str] | None:
    """Normalize a visit_month string to a list of DB-compatible values.

    Handles full names, 3-letter abbreviations, numeric strings, and seasons.
    Returns None if the input cannot be recognized.
    """
    key = raw.strip().lower()

    # Check season first (expands to multiple months)
    if key in _SEASON_TO_MONTHS:
        result: list[str] = []
        for month_key in _SEASON_TO_MONTHS[key]:
            result.extend(_MONTH_NAME_TO_DB_VALUES[month_key])
        return result

    # Check full month name
    if key in _MONTH_NAME_TO_DB_VALUES:
        return list(_MONTH_NAME_TO_DB_VALUES[key])

    # Check 3-letter abbreviation
    if key in _MONTH_ABBR_TO_FULL:
        full = _MONTH_ABBR_TO_FULL[key]
        return list(_MONTH_NAME_TO_DB_VALUES[full])

    # Check numeric string
    if key in _MONTH_NUM_TO_FULL:
        full = _MONTH_NUM_TO_FULL[key]
        return list(_MONTH_NAME_TO_DB_VALUES[full])

    return None


def _normalize_park_params(params: dict[str, Any]) -> dict[str, Any]:
    """Normalize parameters for the search_parks function."""
    cleaned: dict[str, Any] = {}

    if "visited" in params and params["visited"] is not None:
        cleaned["visited"] = bool(params["visited"])

    if "visit_year" in params and params["visit_year"] is not None:
        try:
            val = int(params["visit_year"])
            if 2000 <= val <= 2100:
                cleaned["visit_year"] = val
        except (ValueError, TypeError):
            pass

    if "visit_month" in params and params["visit_month"] is not None:
        normalized = _normalize_visit_month(str(params["visit_month"]))
        if normalized:
            cleaned["visit_month"] = normalized

    # Infer visited=True when visit timing is specified, since having a
    # visit_year or visit_month implies the park was visited.
    if (
        "visit_year" in cleaned or "visit_month" in cleaned
    ) and "visited" not in cleaned:
        cleaned["visited"] = True

    return cleaned


def _normalize_stats_params(params: dict[str, Any]) -> dict[str, Any]:
    """Normalize parameters for the search_stats function."""
    cleaned: dict[str, Any] = {}

    if "hiked" in params and params["hiked"] is not None:
        cleaned["hiked"] = bool(params["hiked"])

    if "per_park" in params and params["per_park"] is not None:
        cleaned["per_park"] = bool(params["per_park"])

    return cleaned


def _normalize_park_summary_params(
    params: dict[str, Any], park_lookup: dict[str, str]
) -> dict[str, Any]:
    """Normalize parameters for the search_park_summary function."""
    cleaned: dict[str, Any] = {}

    raw = params.get("park_code")
    if raw:
        resolved = resolve_park_code(str(raw), park_lookup)
        if resolved:
            cleaned["park_code"] = resolved
        else:
            raise LlmResponseError(
                f"Could not resolve park code '{raw}'. Try using a known park name.",
                context={"park_code": str(raw)},
            )
    else:
        raise LlmResponseError(
            "search_park_summary requires a park_code parameter. "
            "Try specifying which park you want to know about.",
            context={"params": params},
        )

    return cleaned


def _normalize_topic_search_params(
    params: dict[str, Any], park_lookup: dict[str, str]
) -> dict[str, Any]:
    """Normalize parameters for the search_by_topic function."""
    cleaned: dict[str, Any] = {}

    raw_query = params.get("query")
    if not raw_query or not str(raw_query).strip():
        raise LlmResponseError(
            "search_by_topic requires a query parameter. "
            "Try describing what you're looking for.",
            context={"params": params},
        )
    cleaned["query"] = str(raw_query).strip()

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

    if "limit" in params and params["limit"] is not None:
        try:
            val = int(params["limit"])
            cleaned["limit"] = max(1, min(val, 50))
        except (ValueError, TypeError):
            pass

    return cleaned

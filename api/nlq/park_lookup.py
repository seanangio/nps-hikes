"""Park name to park_code resolution for natural language queries.

Builds a cached lookup table from the database and provides fuzzy matching
so the LLM can reference parks by name (e.g., "Yosemite") and we resolve
to the canonical 4-letter code (e.g., "yose").
"""

from __future__ import annotations

import difflib
import re

from api.queries import fetch_all_parks

_park_lookup_cache: dict[str, str] | None = None

# Common suffixes to strip for short-name matching
_DESIGNATION_SUFFIXES = [
    " national park & preserve",
    " national park and preserve",
    " national parks",
    " national and state parks",
    " national park",
]


def get_park_lookup() -> dict[str, str]:
    """Build and cache a park name -> park_code mapping.

    Queries the database once and indexes parks by:
    - Full park name (lowercase)
    - Short name without designation suffix (lowercase)
    - Park code itself

    Returns:
        Dict mapping lowercase name variants to 4-char park codes.
    """
    global _park_lookup_cache
    if _park_lookup_cache is not None:
        return _park_lookup_cache

    result = fetch_all_parks()
    lookup: dict[str, str] = {}

    for park in result["parks"]:
        code = park["park_code"]
        name = park.get("park_name") or ""
        full = park.get("full_name") or ""

        # Index by park code
        lookup[code] = code

        # Index by short park name
        if name:
            lookup[name.lower()] = code

        # Index by full name
        if full:
            lookup[full.lower()] = code

            # Index by short name (strip designation suffixes)
            short = full.lower()
            for suffix in _DESIGNATION_SUFFIXES:
                if short.endswith(suffix):
                    short = short[: -len(suffix)].strip()
                    break
            if short != full.lower():
                lookup[short] = code

    _park_lookup_cache = lookup
    return lookup


def resolve_park_code(
    name_or_code: str, lookup: dict[str, str] | None = None
) -> str | None:
    """Resolve a park name or code to the canonical 4-letter park_code.

    Tries exact match first, then falls back to fuzzy matching.

    Args:
        name_or_code: A park name, abbreviation, or code.
        lookup: Optional pre-built lookup dict. If None, uses cached global.

    Returns:
        The 4-char park_code, or None if no match found.
    """
    if lookup is None:
        lookup = get_park_lookup()

    key = name_or_code.strip().lower()

    # Direct match
    if key in lookup:
        return lookup[key]

    # If it looks like a 4-char code already, return it directly
    if re.match(r"^[a-z]{4}$", key):
        return key

    # Fuzzy match against known names
    matches = difflib.get_close_matches(key, lookup.keys(), n=1, cutoff=0.6)
    if matches:
        return lookup[matches[0]]

    return None


def clear_park_lookup_cache() -> None:
    """Clear the cached park lookup. Useful for testing."""
    global _park_lookup_cache
    _park_lookup_cache = None


def build_park_lookup_text(lookup: dict[str, str]) -> str:
    """Build a compact text table of park names and codes for the LLM prompt.

    Returns only unique code -> name mappings (avoids duplicates from
    multiple name variants mapping to the same code).

    Args:
        lookup: The park lookup dict from get_park_lookup().

    Returns:
        A newline-separated string of "code: Name" entries.
    """
    # Invert to get code -> longest name (most descriptive)
    code_to_name: dict[str, str] = {}
    for name, code in lookup.items():
        if code == name:
            continue  # Skip code -> code self-mappings
        if code not in code_to_name or len(name) > len(code_to_name[code]):
            code_to_name[code] = name

    lines = []
    for code in sorted(code_to_name):
        lines.append(f"- {code_to_name[code]} → {code}")
    return "\n".join(lines)

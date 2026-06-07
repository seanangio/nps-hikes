"""Pre-commit hook to validate JSON examples in docs against API schemas.

Scans Markdown files for annotated JSON code blocks and validates each
against the corresponding Pydantic response model's JSON schema. Blocks
are annotated with HTML comments like:

    <!-- response: GET /parks -->
    ```json
    { ... }
    ```

Unannotated JSON blocks are skipped (those are handled by the syntax-only
check_json_codeblocks.py hook).

Partial examples are supported: truncated arrays ([...] -> []) and
standalone '...' lines are sanitized before validation. The schema is
patched to remove 'required' constraints (doc examples may omit fields)
and add 'additionalProperties: false' (catches renamed or bogus fields).

Usage:
    python scripts/hooks/validate_json_schema.py docs/**/*.md
"""

import argparse
import copy
import json
import re
import sys
from pathlib import Path

# Ensure the project root is on sys.path so 'api.models' is importable
# when this script is invoked as 'python scripts/hooks/validate_json_schema.py'.
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import jsonschema

# Maps "METHOD /path" annotations to Pydantic model class names in api.models
ENDPOINT_MODELS: dict[str, str] = {
    "GET /parks": "ParksResponse",
    "GET /trails": "TrailsResponse",
}

# Regex: HTML comment annotation followed by a ```json fenced code block
ANNOTATED_BLOCK = re.compile(
    r"<!--\s*response:\s*(GET|POST|PUT|PATCH|DELETE)\s+(/\S+)\s*-->"
    r"\s*\n"
    r"```json\s*\n"
    r"(.*?)"
    r"\n```",
    re.DOTALL,
)

# Sanitization patterns (same as check_json_codeblocks.py)
INLINE_ELLIPSIS = re.compile(r"\[\.\.\.\]")
STANDALONE_ELLIPSIS = re.compile(r"^\s*\.\.\.\s*$", re.MULTILINE)
TRAILING_COMMA = re.compile(r",(\s*[\]\}])")


def sanitize_json(content: str) -> str:
    """Replace ellipsis patterns with valid JSON so the rest can be parsed.

    Handles two patterns:
    - '[...]' inline (e.g., "trails": [...]) -> replaced with '[]'
    - '...' on its own line (e.g., omitted array elements) -> line removed

    After removal, trailing commas before ] or } are stripped.
    """
    result = INLINE_ELLIPSIS.sub("[]", content)
    result = STANDALONE_ELLIPSIS.sub("", result)
    result = TRAILING_COMMA.sub(r"\1", result)
    return result


def _patch_object(schema: dict) -> None:
    """Patch an object schema in place for doc example validation.

    - Removes 'required' (doc examples may omit fields)
    - Adds 'additionalProperties: false' (catches bogus/renamed fields)
    """
    if schema.get("type") == "object" and "properties" in schema:
        schema.pop("required", None)
        schema["additionalProperties"] = False


def make_schema_permissive(schema: dict) -> dict:
    """Deep-copy and patch a JSON schema for partial doc example validation.

    Walks the schema and all $defs, removing 'required' and adding
    'additionalProperties: false' to every object definition.
    """
    schema = copy.deepcopy(schema)

    _patch_object(schema)

    for defn in schema.get("$defs", {}).values():
        _patch_object(defn)

    return schema


def build_schemas() -> dict[str, dict]:
    """Build patched JSON schemas for each endpoint in ENDPOINT_MODELS.

    Imports Pydantic models from api.models and generates permissive
    schemas suitable for validating partial doc examples.

    Returns a dict mapping "METHOD /path" to the patched JSON schema.
    """
    import api.models as models_module

    schemas: dict[str, dict] = {}
    for endpoint, model_name in ENDPOINT_MODELS.items():
        model_class = getattr(models_module, model_name)
        raw_schema = model_class.model_json_schema()
        schemas[endpoint] = make_schema_permissive(raw_schema)

    return schemas


def extract_annotated_blocks(
    text: str, filepath: str
) -> list[tuple[int, str, str, str]]:
    """Extract annotated JSON code blocks from Markdown text.

    Finds HTML comments like <!-- response: GET /parks --> followed by
    a ```json fenced code block.

    Returns a list of (line_number, method, path, json_content) tuples.
    Line numbers are 1-based and point to the ```json line.
    """
    blocks: list[tuple[int, str, str, str]] = []

    for match in ANNOTATED_BLOCK.finditer(text):
        method = match.group(1)
        path = match.group(2)
        json_content = match.group(3)

        # Calculate line number of the ```json line
        text_before = text[: match.start(3)]
        line_num = text_before.count("\n") + 1

        blocks.append((line_num, method, path, json_content))

    return blocks


def validate_block(instance: object, schema: dict) -> list[str]:
    """Validate a parsed JSON instance against a schema.

    Returns a list of human-readable error messages.
    """
    validator = jsonschema.Draft202012Validator(schema)
    errors: list[str] = []

    for error in sorted(validator.iter_errors(instance), key=lambda e: list(e.path)):
        json_path = ".".join(str(p) for p in error.absolute_path) or "(root)"
        errors.append(f"{json_path}: {error.message}")

    return errors


def check_file(filepath: str, schemas: dict[str, dict]) -> list[str]:
    """Validate annotated JSON blocks in a Markdown file.

    Returns a list of FAIL strings for any validation errors.
    """
    path = Path(filepath)
    text = path.read_text(encoding="utf-8")
    blocks = extract_annotated_blocks(text, filepath)
    errors: list[str] = []

    for line_num, method, url_path, json_content in blocks:
        endpoint = f"{method} {url_path}"

        if endpoint not in schemas:
            errors.append(
                f"{filepath}:{line_num}: unknown endpoint '{endpoint}' "
                f"(not in ENDPOINT_MODELS)"
            )
            continue

        sanitized = sanitize_json(json_content)

        try:
            instance = json.loads(sanitized)
        except json.JSONDecodeError as exc:
            errors.append(
                f"{filepath}:{line_num} ({endpoint}): "
                f"invalid JSON after sanitization: {exc.msg}"
            )
            continue

        schema = schemas[endpoint]
        validation_errors = validate_block(instance, schema)
        for msg in validation_errors:
            errors.append(f"{filepath}:{line_num} ({endpoint}): {msg}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate JSON examples in docs against API schemas"
    )
    parser.add_argument("files", nargs="+", help="Markdown files to check")
    args = parser.parse_args()

    schemas = build_schemas()
    all_errors: list[str] = []

    for filepath in args.files:
        path = Path(filepath)
        if not path.exists() or path.suffix != ".md":
            continue
        all_errors.extend(check_file(filepath, schemas))

    for error in all_errors:
        print(f"FAIL {error}")

    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main())

"""Pre-commit hook to syntax-check JSON inside Markdown fenced code blocks.

Scans Markdown files for ```json fenced code blocks and checks each
one with json.loads(). Blocks containing ellipsis patterns are sanitized
before checking: '[...]' is replaced with '[]', standalone '...' lines
are removed, and trailing commas left behind are stripped. This allows
structural checking (mismatched braces, missing quotes, etc.) even in
partial examples.

Limitation: This only checks JSON syntax. It does not validate that
response examples match the actual API schema or that field values
are realistic. See validate_json_schema.py for schema validation.
Unusual ellipsis usage could produce false positives.

Usage:
    python scripts/hooks/check_json_codeblocks.py docs/**/*.md
"""

import argparse
import json
import re
import sys
from pathlib import Path

FENCE_OPEN = re.compile(r"^```json\b")
FENCE_CLOSE = re.compile(r"^```\s*$")

# Sanitization patterns for partial JSON examples
INLINE_ELLIPSIS = re.compile(r"\[\.\.\.\]")
STANDALONE_ELLIPSIS = re.compile(r"^\s*\.\.\.\s*$", re.MULTILINE)
TRAILING_COMMA = re.compile(r",(\s*[\]\}])")


def extract_json_blocks(text: str) -> list[tuple[int, str]]:
    """Extract JSON fenced code blocks from Markdown text.

    Returns a list of (start_line_number, block_content) tuples.
    Line numbers are 1-based.
    """
    blocks: list[tuple[int, str]] = []
    lines = text.splitlines()
    in_block = False
    block_start = 0
    block_lines: list[str] = []

    for i, line in enumerate(lines):
        if not in_block:
            if FENCE_OPEN.match(line.strip()):
                in_block = True
                block_start = i + 1  # 1-based, points to the ``` line
                block_lines = []
        else:
            if FENCE_CLOSE.match(line.strip()):
                in_block = False
                blocks.append((block_start, "\n".join(block_lines)))
            else:
                block_lines.append(line)

    return blocks


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


def validate_file(path: Path) -> list[str]:
    """Validate JSON code blocks in a single Markdown file.

    Returns a list of error messages (empty if all blocks are valid).
    """
    text = path.read_text(encoding="utf-8")
    blocks = extract_json_blocks(text)
    errors: list[str] = []

    for line_num, content in blocks:
        sanitized = sanitize_json(content)

        try:
            json.loads(sanitized)
        except json.JSONDecodeError as exc:
            error_line = line_num + exc.lineno
            errors.append(
                f"{path}:{error_line}: {exc.msg} (line {exc.lineno}, col {exc.colno})"
            )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate JSON in Markdown fenced code blocks"
    )
    parser.add_argument("files", nargs="+", help="Markdown files to check")
    args = parser.parse_args()

    all_errors: list[str] = []

    for filepath in args.files:
        path = Path(filepath)
        if not path.exists() or path.suffix != ".md":
            continue
        all_errors.extend(validate_file(path))

    for error in all_errors:
        print(f"FAIL {error}")

    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main())

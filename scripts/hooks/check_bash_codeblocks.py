"""Pre-commit hook to syntax-check bash inside Markdown fenced code blocks.

Scans Markdown files for ```bash fenced code blocks and checks each
one with `bash -n` (syntax-only mode). This catches parse errors like
unclosed quotes, mismatched braces, and malformed control structures
without executing the commands.

Limitation: This only checks bash syntax. It does not verify that
commands exist, that arguments are valid, or that the commands would
succeed when run. It also won't catch issues in blocks tagged as
```sh or ```shell — only ```bash.

Usage:
    python scripts/hooks/check_bash_codeblocks.py *.md
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

FENCE_OPEN = re.compile(r"^```bash\b")
FENCE_CLOSE = re.compile(r"^```\s*$")


def extract_bash_blocks(text: str) -> list[tuple[int, str]]:
    """Extract bash fenced code blocks from Markdown text.

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


def validate_file(path: Path) -> list[str]:
    """Validate bash code blocks in a single Markdown file.

    Returns a list of error messages (empty if all blocks are valid).
    """
    text = path.read_text(encoding="utf-8")
    blocks = extract_bash_blocks(text)
    errors: list[str] = []

    for line_num, content in blocks:
        result = subprocess.run(
            ["bash", "-n"],
            input=content,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            # bash -n reports errors referencing /dev/stdin; replace with
            # the actual file path and line offset for useful output.
            for stderr_line in result.stderr.strip().splitlines():
                msg = stderr_line.replace("/dev/stdin", f"{path}:{line_num}")
                errors.append(msg)

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Syntax-check bash in Markdown fenced code blocks"
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

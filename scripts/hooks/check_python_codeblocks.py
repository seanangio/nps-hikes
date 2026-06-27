"""Pre-commit hook to lint Python inside Markdown fenced code blocks.

Scans Markdown files for ```python fenced code blocks, writes each block to a
temporary .py file, and runs `ruff check` on those files. This extends
blacken-docs: blacken-docs formats snippets and catches syntax errors, while
Ruff catches lint issues such as unused imports, undefined names, and import
ordering.

Usage:
    python scripts/hooks/check_python_codeblocks.py docs/**/*.md
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

FENCE_OPEN = re.compile(r"^```python\b")
FENCE_CLOSE = re.compile(r"^```\s*$")


@dataclass(frozen=True)
class PythonBlock:
    """A Python code block extracted from Markdown."""

    source_path: Path
    fence_line: int
    content: str


@dataclass(frozen=True)
class LintError:
    """A Ruff error mapped back to the source Markdown file."""

    source_path: Path
    line: int
    column: int
    code: str
    message: str

    def format(self) -> str:
        return (
            f"{self.source_path}:{self.line}:{self.column}: {self.code} {self.message}"
        )


def extract_python_blocks(text: str, source_path: Path) -> list[PythonBlock]:
    """Extract Python fenced code blocks from Markdown text.

    The stored line number points to the opening ```python fence. Ruff reports
    line numbers inside the extracted block, so row 1 maps to fence_line + 1.
    """
    blocks: list[PythonBlock] = []
    lines = text.splitlines()
    in_block = False
    block_start = 0
    block_lines: list[str] = []

    for i, line in enumerate(lines):
        if not in_block:
            if FENCE_OPEN.match(line.strip()):
                in_block = True
                block_start = i + 1
                block_lines = []
        else:
            if FENCE_CLOSE.match(line.strip()):
                in_block = False
                blocks.append(
                    PythonBlock(
                        source_path=source_path,
                        fence_line=block_start,
                        content="\n".join(block_lines),
                    )
                )
            else:
                block_lines.append(line)

    return blocks


def _write_temp_blocks(
    blocks: list[PythonBlock], temp_dir: Path
) -> dict[str, PythonBlock]:
    temp_to_block: dict[str, PythonBlock] = {}

    for i, block in enumerate(blocks):
        temp_path = temp_dir / f"block_{i}.py"
        temp_path.write_text(f"{block.content}\n", encoding="utf-8")
        temp_to_block[str(temp_path)] = block

    return temp_to_block


def run_ruff(blocks: list[PythonBlock], config: Path) -> list[str]:
    """Run Ruff against extracted blocks and return mapped error messages."""
    if not blocks:
        return []

    with tempfile.TemporaryDirectory(prefix="markdown-python-") as temp_name:
        temp_dir = Path(temp_name)
        temp_to_block = _write_temp_blocks(blocks, temp_dir)

        command = ["ruff", "check", "--output-format", "json"]
        if config.exists():
            command.extend(["--config", str(config)])
        command.extend(temp_to_block)

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            return ["ruff is not installed or is not on PATH"]

        if result.returncode == 0:
            return []

        try:
            diagnostics = json.loads(result.stdout)
        except json.JSONDecodeError:
            output = result.stderr.strip() or result.stdout.strip()
            return [output or "ruff failed without producing diagnostics"]

    errors: list[str] = []
    for diagnostic in diagnostics:
        block = temp_to_block.get(diagnostic["filename"])
        if block is None:
            continue

        location = diagnostic["location"]
        line = block.fence_line + location["row"]
        lint_error = LintError(
            source_path=block.source_path,
            line=line,
            column=location["column"],
            code=diagnostic["code"],
            message=diagnostic["message"],
        )
        errors.append(lint_error.format())

    return errors


def check_file(path: Path, config: Path) -> list[str]:
    """Lint Python code blocks in a single Markdown file."""
    text = path.read_text(encoding="utf-8")
    blocks = extract_python_blocks(text, path)
    return run_ruff(blocks, config)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Lint Python in Markdown fenced code blocks with Ruff"
    )
    parser.add_argument("files", nargs="+", help="Markdown files to check")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("pyproject.toml"),
        help="Ruff configuration file",
    )
    args = parser.parse_args()

    all_errors: list[str] = []

    for filepath in args.files:
        path = Path(filepath)
        if not path.exists() or path.suffix != ".md":
            continue
        all_errors.extend(check_file(path, args.config))

    for error in all_errors:
        print(f"FAIL {error}")

    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main())

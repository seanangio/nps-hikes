"""Unit tests for the Python code block Ruff hook."""

import json
from pathlib import Path
from types import SimpleNamespace

from scripts.hooks.check_python_codeblocks import (
    PythonBlock,
    check_file,
    extract_python_blocks,
    run_ruff,
)


class TestExtractPythonBlocks:
    """Test extraction of Python fenced code blocks from Markdown."""

    def test_finds_python_block(self):
        text = "# Example\n\n```python\nprint('hello')\n```\n"
        blocks = extract_python_blocks(text, Path("docs/example.md"))

        assert blocks == [
            PythonBlock(
                source_path=Path("docs/example.md"),
                fence_line=3,
                content="print('hello')",
            )
        ]

    def test_multiple_blocks(self):
        text = "```python\nx = 1\n```\n\n```python\ny = 2\n```\n"
        blocks = extract_python_blocks(text, Path("docs/example.md"))

        assert len(blocks) == 2
        assert blocks[0].content == "x = 1"
        assert blocks[1].content == "y = 2"

    def test_ignores_non_python_blocks(self):
        text = "```bash\necho hello\n```\n"
        blocks = extract_python_blocks(text, Path("docs/example.md"))

        assert blocks == []


class TestRunRuff:
    """Test Ruff invocation and Markdown line mapping."""

    def test_no_blocks_returns_no_errors(self):
        assert run_ruff([], Path("pyproject.toml")) == []

    def test_maps_ruff_diagnostics_to_markdown_lines(self, monkeypatch):
        def fake_run(command, capture_output, text, check):
            temp_file = command[-1]
            diagnostic = {
                "filename": temp_file,
                "location": {"row": 2, "column": 5},
                "code": "F821",
                "message": "Undefined name `missing_name`",
            }
            return SimpleNamespace(
                returncode=1,
                stdout=json.dumps([diagnostic]),
                stderr="",
            )

        monkeypatch.setattr(
            "scripts.hooks.check_python_codeblocks.subprocess.run", fake_run
        )

        blocks = [
            PythonBlock(
                source_path=Path("docs/example.md"),
                fence_line=10,
                content="x = 1\nmissing_name",
            )
        ]

        errors = run_ruff(blocks, Path("pyproject.toml"))

        assert errors == ["docs/example.md:12:5: F821 Undefined name `missing_name`"]

    def test_reports_missing_ruff(self, monkeypatch):
        def fake_run(command, capture_output, text, check):
            raise FileNotFoundError

        monkeypatch.setattr(
            "scripts.hooks.check_python_codeblocks.subprocess.run", fake_run
        )

        blocks = [
            PythonBlock(
                source_path=Path("docs/example.md"),
                fence_line=1,
                content="print('hello')",
            )
        ]

        assert run_ruff(blocks, Path("pyproject.toml")) == [
            "ruff is not installed or is not on PATH"
        ]


class TestCheckFile:
    """End-to-end checks with temporary Markdown files."""

    def test_file_without_python_blocks_has_no_errors(self, tmp_path):
        markdown = tmp_path / "example.md"
        markdown.write_text("```json\n{}\n```\n", encoding="utf-8")

        assert check_file(markdown, Path("pyproject.toml")) == []

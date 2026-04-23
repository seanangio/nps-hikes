"""Review writing for AI patterns using a local Ollama LLM.

Sends document content to a local LLM with instructions to detect (or rewrite)
AI writing patterns. Uses the same Ollama instance and model configured for the
NLQ endpoint.

Usage:
    # Activate the virtualenv first
    source ~/.virtualenvs/nps-hikes/bin/activate

    # Detect AI patterns in a single file (default mode)
    python scripts/tools/review_writing.py docs/index.md

    # Rewrite mode (returns cleaned version + diff summary)
    python scripts/tools/review_writing.py docs/index.md --rewrite

    # Multiple files
    python scripts/tools/review_writing.py docs/index.md docs/api-tutorial.md

    # All markdown files in a directory
    python scripts/tools/review_writing.py docs/

Requirements:
    - Ollama must be running locally. Start it with: ollama serve
    - A model must be pulled. The default model is configured in config/settings.py
      (OLLAMA_MODEL, default: llama3.1:8b). Pull it with: ollama pull llama3.1:8b
    - See docs/getting-started.md "Prerequisites" section for full Ollama setup.

Configuration:
    The script reads Ollama settings from config/settings.py, which loads from
    environment variables. Override with:
        OLLAMA_BASE_URL  (default: http://localhost:11434)
        OLLAMA_MODEL     (default: llama3.1:8b)
        OLLAMA_TIMEOUT   (default: 60s — increase for large files or slow hardware)

Output:
    Saves results to reviews/<timestamp>.md in the project root.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import httpx

# Ensure project root is on sys.path so config imports work
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import config

SKILL_FILE = Path.home() / ".claude" / "skills" / "avoid-ai-writing" / "SKILL.md"
REVIEWS_DIR = PROJECT_ROOT / "reviews"


def load_skill_instructions() -> str:
    """Read the SKILL.md file that defines the AI-writing audit rules."""
    if not SKILL_FILE.exists():
        print(f"Error: Skill file not found at {SKILL_FILE}")
        sys.exit(1)
    return SKILL_FILE.read_text()


def collect_files(paths: list[str]) -> list[Path]:
    """Resolve input paths to a list of markdown files.

    Accepts individual files or directories. Directories are expanded to
    all *.md files (non-recursive).
    """
    files: list[Path] = []
    for p in paths:
        path = Path(p)
        if not path.exists():
            print(f"Warning: {p} does not exist, skipping")
            continue
        if path.is_dir():
            md_files = sorted(path.glob("*.md"))
            if not md_files:
                print(f"Warning: no .md files found in {p}, skipping")
            files.extend(md_files)
        elif path.is_file():
            files.append(path)
        else:
            print(f"Warning: {p} is not a file or directory, skipping")
    return files


def build_messages(
    skill_instructions: str, file_content: str, file_path: str, rewrite: bool
) -> list[dict[str, str]]:
    """Build the chat messages for Ollama.

    The system message contains the full SKILL.md instructions with the
    context profile set to 'docs'. The user message contains the file
    content and the requested mode.
    """
    mode = "rewrite" if rewrite else "detect"

    system_message = f"{skill_instructions}\n\nContext profile: docs\nMode: {mode}\n"

    user_message = (
        f"Review the following file ({file_path}) in {mode} mode:\n\n{file_content}"
    )

    return [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message},
    ]


def call_ollama(messages: list[dict[str, str]]) -> str:
    """Send a chat request to Ollama and return the response text.

    Uses a longer timeout than the default since review of large documents
    can take a while on CPU.
    """
    url = f"{config.OLLAMA_BASE_URL}/api/chat"
    # Use 3x the configured timeout — reviews are longer than NLQ queries
    timeout = config.OLLAMA_TIMEOUT * 3
    payload = {
        "model": config.OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
    }

    try:
        with httpx.Client(timeout=httpx.Timeout(timeout)) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()
            content: str = result["message"]["content"]
            return content
    except httpx.ConnectError:
        print(
            f"Error: Cannot connect to Ollama at {config.OLLAMA_BASE_URL}\n"
            "Is Ollama running? Start it with: ollama serve"
        )
        sys.exit(1)
    except httpx.TimeoutException:
        print(
            f"Error: Ollama request timed out after {timeout}s.\n"
            "The model may still be loading, or the file may be too large.\n"
            "Try increasing OLLAMA_TIMEOUT in your environment."
        )
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"Error: Ollama returned HTTP {e.response.status_code}")
        sys.exit(1)


def save_review(content: str, output_path: Path) -> None:
    """Write the review content to the output file."""
    REVIEWS_DIR.mkdir(exist_ok=True)
    output_path.write_text(content)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Review writing for AI patterns using a local Ollama LLM."
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="Files or directories to review. Directories expand to all *.md files.",
    )
    parser.add_argument(
        "--rewrite",
        action="store_true",
        help="Rewrite mode: flag AI patterns and return a cleaned version. "
        "Default is detect mode (flag only, no rewriting).",
    )
    args = parser.parse_args()

    files = collect_files(args.paths)
    if not files:
        print("No files to review.")
        sys.exit(1)

    skill_instructions = load_skill_instructions()
    mode_label = "rewrite" if args.rewrite else "detect"
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_path = REVIEWS_DIR / f"{timestamp}.md"

    sections: list[str] = []

    for i, file_path in enumerate(files, 1):
        print(f"[{i}/{len(files)}] Reviewing {file_path} ({mode_label} mode)...")

        file_content = file_path.read_text()
        messages = build_messages(
            skill_instructions, file_content, str(file_path), args.rewrite
        )
        review = call_ollama(messages)
        sections.append(f"# Review: {file_path}\n\n{review}")

    output_content = "\n\n---\n\n".join(sections) + "\n"
    save_review(output_content, output_path)

    line_count = output_content.count("\n")
    print(f"\nDone. Review saved to {output_path} ({line_count} lines)")


if __name__ == "__main__":
    main()

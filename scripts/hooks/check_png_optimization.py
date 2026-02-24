"""Pre-commit hook to check that PNG files are reasonably optimized.

Re-compresses each PNG with Pillow at maximum compression and fails
if the original is more than --threshold percent larger than the
optimized version.

Usage:
    # Check mode (default) — exits non-zero if any file is unoptimized
    python scripts/hooks/check_png_optimization.py image.png

    # Fix mode — overwrites files with optimized versions
    python scripts/hooks/check_png_optimization.py --fix image.png
"""

import argparse
import io
import sys
from pathlib import Path

from PIL import Image


def get_optimized_size(path: Path) -> int:
    """Return the size in bytes of the PNG re-compressed at max level."""
    buf = io.BytesIO()
    with Image.open(path) as img:
        img.save(buf, format="PNG", optimize=True, compress_level=9)
    return buf.tell()


def optimize_file(path: Path) -> None:
    """Overwrite a PNG with its optimized version."""
    with Image.open(path) as img:
        img.save(path, format="PNG", optimize=True, compress_level=9)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check PNG optimization")
    parser.add_argument("files", nargs="+", help="PNG files to check")
    parser.add_argument(
        "--threshold",
        type=float,
        default=10.0,
        help="Fail if a file could shrink by more than this percentage (default: 10)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Overwrite files with optimized versions instead of just checking",
    )
    args = parser.parse_args()

    failed = False
    for filepath in args.files:
        path = Path(filepath)
        if not path.exists():
            continue

        original_size = path.stat().st_size
        if original_size == 0:
            continue

        optimized_size = get_optimized_size(path)
        savings_pct = (1 - optimized_size / original_size) * 100

        if savings_pct > args.threshold:
            if args.fix:
                optimize_file(path)
                print(
                    f"Optimized {path}: {original_size:,} -> {optimized_size:,} bytes "
                    f"({savings_pct:.1f}% smaller)"
                )
            else:
                print(
                    f"FAIL {path}: could shrink by {savings_pct:.1f}% "
                    f"({original_size:,} -> {optimized_size:,} bytes). "
                    f"Run: python scripts/hooks/check_png_optimization.py --fix {path}"
                )
                failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

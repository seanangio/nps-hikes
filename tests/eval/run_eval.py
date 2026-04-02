#!/usr/bin/env python
"""Evaluate NLQ routing accuracy against a golden dataset.

Runs each query through the full NLQ pipeline (prompt → Ollama → parse →
validate) and compares the extracted function and parameters against
expected values.

Requires:
  - Ollama running locally with the target model loaded
  - PostgreSQL database running (for park lookup)

Usage:
  python tests/eval/run_eval.py
  python tests/eval/run_eval.py --model qwen2.5:7b
  python tests/eval/run_eval.py --runs 3
  python tests/eval/run_eval.py --threshold 0.8
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from api.nlq.ollama_client import call_ollama
from api.nlq.park_lookup import build_park_lookup_text, get_park_lookup
from api.nlq.parser import parse_tool_call, validate_and_normalize
from api.nlq.prompt import TOOLS, build_chat_messages, build_system_message
from config.settings import config
from utils.exceptions import LlmConnectionError, LlmResponseError


def load_golden_queries(path: Path) -> list[dict[str, Any]]:
    """Load the golden query dataset from JSON."""
    with open(path) as f:
        data: list[dict[str, Any]] = json.load(f)
    return data


async def run_single_query(
    query: str, system_message: str, park_lookup: dict[str, str]
) -> dict[str, Any]:
    """Run a single query through the NLQ pipeline.

    Returns a dict with function, params, error, and elapsed time.
    """
    messages = build_chat_messages(query, system_message)
    start = time.time()
    raw_response: dict[str, Any] = {}
    try:
        response = await call_ollama(messages, TOOLS)
        raw_response = response.get("message", {})
        function_name, raw_params = parse_tool_call(response)
        function_name, params = validate_and_normalize(
            function_name, raw_params, park_lookup, query=query
        )
        elapsed = time.time() - start
        return {
            "function": function_name,
            "params": params,
            "error": None,
            "elapsed": elapsed,
            "raw_response": raw_response,
        }
    except (LlmResponseError, LlmConnectionError) as e:
        elapsed = time.time() - start
        return {
            "function": None,
            "params": {},
            "error": str(e),
            "elapsed": elapsed,
            "raw_response": raw_response,
        }


def check_result(expected: dict[str, Any], actual: dict[str, Any]) -> tuple[str, str]:
    """Compare expected vs actual result.

    Returns:
        A tuple of (status, detail) where status is PASS, PARTIAL, or FAIL.
        - PASS: correct function and all expected params match
        - PARTIAL: correct function but one or more expected params wrong/missing
        - FAIL: wrong function or pipeline error
    """
    if actual["error"]:
        return "FAIL", f"Error: {actual['error']}"

    if actual["function"] != expected["expected_function"]:
        return "FAIL", (
            f"Wrong function: expected {expected['expected_function']}, "
            f"got {actual['function']}"
        )

    # Check expected params (subset match — extra params from LLM are OK)
    expected_params = expected.get("expected_params", {})
    mismatches = []
    for key, expected_val in expected_params.items():
        actual_val = actual["params"].get(key)
        # Handle float/int comparison (e.g., 3.0 == 3)
        if isinstance(expected_val, (int, float)) and isinstance(
            actual_val, (int, float)
        ):
            if float(expected_val) != float(actual_val):
                mismatches.append(
                    f"{key}: expected {expected_val!r}, got {actual_val!r}"
                )
        elif actual_val != expected_val:
            mismatches.append(f"{key}: expected {expected_val!r}, got {actual_val!r}")

    if mismatches:
        return "PARTIAL", "; ".join(mismatches)

    return "PASS", ""


async def run_eval(
    golden: list[dict[str, Any]],
    system_message: str,
    park_lookup: dict[str, str],
    runs: int,
) -> list[dict[str, Any]]:
    """Run all golden queries and return results."""
    results: list[dict[str, Any]] = []

    for run_num in range(runs):
        if runs > 1:
            print(f"\n--- Run {run_num + 1}/{runs} ---")

        for i, case in enumerate(golden, 1):
            query = case["query"]
            label = query if len(query) <= 55 else query[:52] + "..."
            print(f"  [{i:2d}/{len(golden)}] {label:<55s}", end="", flush=True)

            actual = await run_single_query(query, system_message, park_lookup)
            status, detail = check_result(case, actual)

            results.append(
                {
                    "run": run_num + 1,
                    "query": query,
                    "category": case.get("category", "unknown"),
                    "expected_function": case["expected_function"],
                    "expected_params": case.get("expected_params", {}),
                    "actual_function": actual["function"],
                    "actual_params": actual["params"],
                    "status": status,
                    "detail": detail,
                    "elapsed": actual["elapsed"],
                    "raw_response": actual["raw_response"],
                }
            )

            symbol = {"PASS": "+", "PARTIAL": "~", "FAIL": "X"}[status]
            print(f" [{symbol}] ({actual['elapsed']:.1f}s)")

    return results


def print_summary(results: list[dict[str, Any]], model: str, runs: int) -> float:
    """Print the evaluation summary. Returns the pass rate."""
    total = len(results)
    pass_count = sum(1 for r in results if r["status"] == "PASS")
    partial_count = sum(1 for r in results if r["status"] == "PARTIAL")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")
    pass_rate = pass_count / total

    print(f"\n{'=' * 60}")
    print(f"Model: {model} | Runs: {runs} | Queries per run: {total // runs}")
    print(f"{'=' * 60}")

    print(f"\nOverall: {pass_count}/{total} pass ({pass_rate:.1%})")
    print(f"  PASS: {pass_count}  PARTIAL: {partial_count}  FAIL: {fail_count}")

    # Per category
    categories = sorted(set(r["category"] for r in results))
    print("\nPer tool:")
    for cat in categories:
        cat_results = [r for r in results if r["category"] == cat]
        cat_pass = sum(1 for r in cat_results if r["status"] == "PASS")
        cat_total = len(cat_results)
        pct = cat_pass / cat_total * 100
        print(f"  {cat:<25s} {cat_pass:2d}/{cat_total:2d} ({pct:.1f}%)")

    # Latency
    avg_elapsed = sum(r["elapsed"] for r in results) / total
    max_elapsed = max(r["elapsed"] for r in results)
    print(f"\nLatency: avg {avg_elapsed:.1f}s, max {max_elapsed:.1f}s")

    # Failures
    failures = [r for r in results if r["status"] != "PASS"]
    if failures:
        print(f"\n{'-' * 60}")
        print(f"FAILURES ({len(failures)}):\n")
        for r in failures:
            print(f'  "{r["query"]}"')
            print(f"    expected: {r['expected_function']} {r['expected_params']}")
            print(f"    got:      {r['actual_function']} {r['actual_params']}")
            if r["detail"]:
                print(f"    reason:   {r['detail']}")
            print(f"    status:   {r['status']}")
            print()

    return pass_rate


def save_results(
    results: list[dict[str, Any]], model: str, runs: int, pass_rate: float
) -> Path:
    """Save full results to a JSON file in eval_results/.

    Filename format: YYYY-MM-DD_model-name.json
    If a file with the same name exists, a numeric suffix is appended.

    Returns the path to the saved file.
    """
    # Build output directory at project root
    project_root = Path(__file__).parent.parent.parent
    output_dir = project_root / "eval_results"
    output_dir.mkdir(exist_ok=True)

    # Build filename: sanitize model name for filesystem
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    safe_model = re.sub(r"[^\w\-.]", "-", model)
    base_name = f"{date_str}_{safe_model}"

    # Handle duplicate filenames
    output_path = output_dir / f"{base_name}.json"
    counter = 2
    while output_path.exists():
        output_path = output_dir / f"{base_name}_{counter}.json"
        counter += 1

    # Compute summary stats
    total = len(results)
    pass_count = sum(1 for r in results if r["status"] == "PASS")
    partial_count = sum(1 for r in results if r["status"] == "PARTIAL")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")

    categories = sorted(set(r["category"] for r in results))
    per_tool: dict[str, Any] = {}
    for cat in categories:
        cat_results = [r for r in results if r["category"] == cat]
        cat_pass = sum(1 for r in cat_results if r["status"] == "PASS")
        per_tool[cat] = {
            "pass": cat_pass,
            "total": len(cat_results),
            "rate": round(cat_pass / len(cat_results), 4),
        }

    output = {
        "timestamp": datetime.now(UTC).isoformat(),
        "model": model,
        "runs": runs,
        "queries_per_run": total // runs,
        "summary": {
            "pass_rate": round(pass_rate, 4),
            "pass": pass_count,
            "partial": partial_count,
            "fail": fail_count,
            "total": total,
            "avg_latency_s": round(sum(r["elapsed"] for r in results) / total, 2),
        },
        "per_tool": per_tool,
        "results": results,
    }

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate NLQ routing accuracy against a golden dataset"
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"Ollama model to use (default: {config.OLLAMA_MODEL})",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of times to run each query (default: 1)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.0,
        help="Minimum pass rate to exit with code 0 (default: 0.0, no threshold)",
    )
    args = parser.parse_args()

    # Override model if specified
    if args.model:
        config.OLLAMA_MODEL = args.model
    model = config.OLLAMA_MODEL

    # Load golden dataset
    golden_path = Path(__file__).parent / "golden_queries.json"
    golden = load_golden_queries(golden_path)
    print(f"Loaded {len(golden)} golden queries from {golden_path.name}")

    # Build park lookup (requires live DB)
    print("Building park lookup from database...")
    park_lookup = get_park_lookup()
    lookup_text = build_park_lookup_text(park_lookup)
    system_message = build_system_message(lookup_text)
    print(f"Park lookup ready ({len(park_lookup)} entries)")

    print(f"\nRunning eval with model: {model}")

    # Run eval
    results = asyncio.run(run_eval(golden, system_message, park_lookup, args.runs))

    # Print summary and save
    pass_rate = print_summary(results, model, args.runs)
    output_path = save_results(results, model, args.runs, pass_rate)
    print(f"\nResults saved to {output_path}")

    # Exit code based on threshold
    if args.threshold > 0 and pass_rate < args.threshold:
        print(f"\nFAILED: pass rate {pass_rate:.1%} < threshold {args.threshold:.1%}")
        sys.exit(1)


if __name__ == "__main__":
    main()

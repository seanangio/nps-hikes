"""Local Streamable HTTP MCP server entrypoint for nps-hikes."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from nps_hikes_mcp.server import (
    DEFAULT_HTTP_HOST,
    DEFAULT_HTTP_PATH,
    DEFAULT_HTTP_PORT,
    run_http_server,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the local HTTP entrypoint."""
    parser = argparse.ArgumentParser(
        description="Run the local nps-hikes MCP server over Streamable HTTP."
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HTTP_HOST,
        help="Host interface to bind to. Defaults to local-only 127.0.0.1.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_HTTP_PORT,
        help=f"Port to bind to. Defaults to {DEFAULT_HTTP_PORT}.",
    )
    parser.add_argument(
        "--path",
        default=DEFAULT_HTTP_PATH,
        help=f"MCP endpoint path. Defaults to {DEFAULT_HTTP_PATH}.",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        help="Optional Uvicorn log level override.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Run the local MCP server over Streamable HTTP."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        run_http_server(
            host=args.host,
            port=args.port,
            path=args.path,
            log_level=args.log_level,
        )
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()

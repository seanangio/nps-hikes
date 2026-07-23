"""Local MCP server helpers and stdio entrypoint for nps-hikes."""

from __future__ import annotations

import asyncio
import importlib
import json
from typing import Any

from nps_hikes_mcp.resources import (
    RESOURCE_DEFINITIONS,
)
from nps_hikes_mcp.tools import TOOL_DEFINITIONS

DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8002
DEFAULT_HTTP_PATH = "/mcp"


def _load_fastmcp() -> type[Any]:
    """Load a FastMCP-compatible class when the dependency is installed."""
    try:
        module = importlib.import_module("fastmcp")
        return module.FastMCP
    except ImportError:
        pass

    try:
        module = importlib.import_module("mcp.server.fastmcp")
        return module.FastMCP
    except ImportError as exc:
        raise RuntimeError(
            "No MCP server library is installed. Install `fastmcp` or a compatible "
            "`mcp` package before running the local server."
        ) from exc


def _load_function_resource() -> type[Any]:
    """Load the FastMCP FunctionResource class when available."""
    try:
        module = importlib.import_module("fastmcp.resources")
        return module.FunctionResource
    except ImportError as exc:
        raise RuntimeError(
            "The installed MCP server library does not expose `fastmcp.resources.FunctionResource`."
        ) from exc


def create_server() -> Any:
    """Create and register the local MCP server."""
    FastMCP = _load_fastmcp()
    FunctionResource = _load_function_resource()
    app = FastMCP("nps-hikes")

    for tool in TOOL_DEFINITIONS:
        app.tool(
            name=tool["name"],
            description=tool["description"],
        )(tool["fn"])

    for resource in RESOURCE_DEFINITIONS:

        def resource_reader(
            reader=resource["reader"],
        ) -> str:
            content = reader()
            if isinstance(content, str):
                return content
            return json.dumps(content, indent=2, sort_keys=True)

        app.add_resource(
            FunctionResource(
                uri=f"resource://{resource['uri']}",
                name=resource["name"],
                description=resource["description"],
                mime_type=resource["mime_type"],
                fn=resource_reader,
            )
        )

    return app


def run_stdio_server() -> None:
    """Run the local MCP server over stdio."""
    server = create_server()
    run_method = getattr(server, "run", None)
    if callable(run_method):
        run_method()
        return

    run_stdio = getattr(server, "run_stdio", None)
    if callable(run_stdio):
        run_stdio()
        return

    raise RuntimeError(
        "Installed MCP server library does not expose a supported run method."
    )


def run_http_server(
    *,
    host: str = DEFAULT_HTTP_HOST,
    port: int = DEFAULT_HTTP_PORT,
    path: str = DEFAULT_HTTP_PATH,
    log_level: str | None = None,
) -> None:
    """Run the local MCP server over local-only Streamable HTTP."""
    server = create_server()
    run_method = getattr(server, "run", None)
    if callable(run_method):
        run_method(
            transport="streamable-http",
            host=host,
            port=port,
            path=path,
            log_level=log_level,
        )
        return

    run_http_async = getattr(server, "run_http_async", None)
    if callable(run_http_async):
        asyncio.run(
            run_http_async(
                transport="streamable-http",
                host=host,
                port=port,
                path=path,
                log_level=log_level,
            )
        )
        return

    raise RuntimeError(
        "Installed MCP server library does not expose a supported HTTP run method."
    )


def main() -> None:
    """Run the local MCP server over stdio."""
    try:
        run_stdio_server()
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()

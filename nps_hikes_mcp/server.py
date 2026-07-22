"""Local stdio MCP server entrypoint for nps-hikes."""

from __future__ import annotations

import importlib
import json
from typing import Any

from nps_hikes_mcp.resources import (
    RESOURCE_DEFINITIONS,
)
from nps_hikes_mcp.tools import TOOL_DEFINITIONS


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


def main() -> None:
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


if __name__ == "__main__":
    main()

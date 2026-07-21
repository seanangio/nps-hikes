"""Local stdio MCP server entrypoint for nps-hikes."""

from __future__ import annotations

import importlib
import json
from typing import Any

from nps_hikes_mcp.resources import (
    RESOURCE_DEFINITIONS,
    read_resource,
)
from nps_hikes_mcp.tools import (
    TOOL_DEFINITIONS,
    McpToolNotFoundError,
    search_park_summary,
    search_parks,
    search_stats,
    search_trails,
)


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

    @app.tool(
        name="search_trails",
        description=TOOL_DEFINITIONS[0]["description"],
    )
    def trails_tool(
        park_code: str | None = None,
        state: str | None = None,
        hiked: bool | None = None,
        min_length: float | None = None,
        max_length: float | None = None,
        source: str | None = None,
        viz_3d: bool | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        return search_trails(
            park_code=park_code,
            state=state,
            hiked=hiked,
            min_length=min_length,
            max_length=max_length,
            source=source,
            viz_3d=viz_3d,
            limit=limit,
        )

    @app.tool(
        name="search_parks",
        description=TOOL_DEFINITIONS[1]["description"],
    )
    def parks_tool(
        visited: bool | None = None,
        visit_year: int | None = None,
        visit_month: str | list[str] | None = None,
        park_code: str | None = None,
        state: str | None = None,
    ) -> dict[str, Any]:
        return search_parks(
            visited=visited,
            visit_year=visit_year,
            visit_month=visit_month,
            park_code=park_code,
            state=state,
        )

    @app.tool(
        name="search_stats",
        description=TOOL_DEFINITIONS[2]["description"],
    )
    def stats_tool(hiked: bool | None = None) -> dict[str, Any]:
        return search_stats(hiked=hiked)

    @app.tool(
        name="search_park_summary",
        description=TOOL_DEFINITIONS[3]["description"],
    )
    def park_summary_tool(park_code: str) -> dict[str, Any]:
        try:
            return search_park_summary(park_code=park_code)
        except McpToolNotFoundError as exc:
            raise ValueError(str(exc)) from exc

    for resource in RESOURCE_DEFINITIONS:
        uri = resource["uri"]

        def resource_reader(resource_uri: str = uri) -> str:
            content = read_resource(resource_uri)
            if isinstance(content, str):
                return content
            return json.dumps(content, indent=2, sort_keys=True)

        app.add_resource(
            FunctionResource(
                uri=f"resource://{uri}",
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

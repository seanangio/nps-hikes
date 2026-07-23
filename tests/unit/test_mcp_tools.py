"""Unit tests for MCP tool and resource wrappers."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from nps_hikes_mcp import http_server
from nps_hikes_mcp import server as mcp_server
from nps_hikes_mcp.resources import (
    RESOURCE_DEFINITIONS,
    get_park_lookup_resource,
    read_resource,
)
from nps_hikes_mcp.tools import (
    TOOL_DEFINITIONS,
    McpToolError,
    McpToolNotFoundError,
    search_by_topic,
    search_park_summary,
    search_parks,
    search_stats,
    search_trails,
)
from utils.exceptions import DatabaseError, LlmConnectionError


def test_search_trails_shapes_result() -> None:
    fake_result = {
        "trail_count": 2,
        "total_miles": 7.5,
        "trails": [
            {
                "trail_id": "1",
                "trail_name": "Angel's Landing",
                "park_code": "zion",
                "park_name": "Zion",
                "states": "UT",
                "source": "TNM",
                "length_miles": 5.4,
                "geometry_type": "LineString",
                "highway_type": None,
                "hiked": True,
                "viz_3d_available": True,
                "viz_3d_slug": "angels_landing",
            },
            {
                "trail_id": "2",
                "trail_name": "Emerald Pools",
                "park_code": "zion",
                "park_name": "Zion",
                "states": "UT",
                "source": "OSM",
                "length_miles": 2.1,
                "geometry_type": "LineString",
                "highway_type": "path",
                "hiked": False,
                "viz_3d_available": False,
                "viz_3d_slug": None,
            },
        ],
        "pagination": {"limit": 50, "offset": 0, "total_count": 2},
    }

    with patch(
        "nps_hikes_mcp.tools.fetch_trails", return_value=fake_result
    ) as mock_fetch:
        result = search_trails(state="UT", max_length=6, limit=10)

    mock_fetch.assert_called_once_with(
        park_code=None,
        state="UT",
        hiked=None,
        min_length=None,
        max_length=6,
        source=None,
        viz_3d=None,
        limit=10,
        offset=0,
        geojson=False,
    )
    assert result["trail_count"] == 2
    assert result["total_miles"] == 7.5
    assert result["applied_filters"] == {"state": "UT", "max_length": 6, "limit": 10}
    assert "matching state UT, max 6 mi" in result["summary"]
    assert "geometry_type" not in result["trails"][0]


def test_search_parks_normalizes_single_visit_month() -> None:
    fake_result = {
        "park_count": 1,
        "visited_count": 1,
        "parks": [
            {
                "park_code": "yose",
                "park_name": "Yosemite",
                "full_name": "Yosemite National Park",
                "states": "CA",
                "visit_month": "July",
                "visit_year": 2023,
                "url": "https://www.nps.gov/yose/index.htm",
            }
        ],
    }

    with patch(
        "nps_hikes_mcp.tools.fetch_all_parks", return_value=fake_result
    ) as mock_fetch:
        result = search_parks(visit_month="July")

    mock_fetch.assert_called_once_with(
        visited=None,
        visit_year=None,
        visit_month=["July"],
        park_code=None,
        state=None,
        description=False,
        boundary=False,
    )
    assert result["applied_filters"] == {"visit_month": ["July"]}
    assert result["parks"][0]["park_code"] == "yose"


def test_search_stats_adds_summary() -> None:
    fake_result = {
        "total_trails": 12,
        "total_miles": 55.5,
        "avg_trail_length": 4.62,
        "parks_count": 3,
        "states_count": 2,
        "source_breakdown": {"tnm": 8, "osm": 4},
        "longest_trail": None,
        "shortest_trail": None,
    }

    with patch("nps_hikes_mcp.tools.fetch_stats", return_value=fake_result):
        result = search_stats(hiked=False)

    assert result["applied_filters"] == {"hiked": False}
    assert "Unhiked trails include 12 trails" in result["summary"]


def test_search_by_topic_shapes_successful_result() -> None:
    fake_result = {
        "trail_count": 1,
        "total_miles": 5.4,
        "trails": [
            {
                "trail_id": "550779",
                "trail_name": "Mist Trail",
                "park_code": "yose",
                "park_name": "Yosemite National Park",
                "states": "CA",
                "source": "TNM",
                "length_miles": 5.4,
                "geometry_type": "LineString",
                "highway_type": None,
                "hiked": True,
                "viz_3d_available": False,
                "viz_3d_slug": None,
                "geometry": {"type": "LineString"},
            }
        ],
        "topic_context": [
            {
                "trail_id": "550779",
                "trail_name": "Mist Trail",
                "park_code": "yose",
                "park_name": "Yosemite National Park",
                "content_title": "Hike to Vernal Fall",
                "chunk_text_preview": "Follow the Mist Trail to see the waterfall.",
                "chunk_text": "Full chunk text should not survive MCP shaping.",
            }
        ],
        "fallback_chunks": [],
    }

    with (
        patch(
            "nps_hikes_mcp.tools.get_embeddings_sync", return_value=[[0.01] * 768]
        ) as mock_embed,
        patch(
            "nps_hikes_mcp.tools.fetch_topic_trails", return_value=fake_result
        ) as mock_fetch,
    ):
        result = search_by_topic(query="waterfalls", state="CA", limit=10)

    mock_embed.assert_called_once_with(["waterfalls"])
    mock_fetch.assert_called_once_with(
        query_embedding=[0.01] * 768,
        park_code=None,
        state="CA",
        hiked=None,
        min_length=None,
        max_length=None,
        source=None,
        limit=10,
        geojson=False,
    )
    assert result["trail_count"] == 1
    assert result["applied_filters"] == {
        "query": "waterfalls",
        "state": "CA",
        "limit": 10,
    }
    assert "matching topic 'waterfalls', state CA" in result["summary"]
    assert "geometry" not in result["trails"][0]
    assert result["topic_context"] == [
        {
            "trail_id": "550779",
            "trail_name": "Mist Trail",
            "park_code": "yose",
            "park_name": "Yosemite National Park",
            "content_title": "Hike to Vernal Fall",
            "chunk_text_preview": "Follow the Mist Trail to see the waterfall.",
        }
    ]


def test_search_by_topic_empty_result_includes_fallback_chunks() -> None:
    fake_result = {
        "trail_count": 0,
        "total_miles": 0.0,
        "trails": [],
        "topic_context": [],
        "fallback_chunks": [
            {
                "title": "Waterfall Views",
                "chunk_text": "Look for overlooks and spray zones.",
                "park_code": "yose",
                "park_name": "Yosemite National Park",
                "source_type": "thingstodo",
                "similarity_score": 0.88,
            }
        ],
    }

    with (
        patch("nps_hikes_mcp.tools.get_embeddings_sync", return_value=[[0.01] * 768]),
        patch("nps_hikes_mcp.tools.fetch_topic_trails", return_value=fake_result),
    ):
        result = search_by_topic(query="waterfalls")

    assert result["trail_count"] == 0
    assert result["fallback_chunks"] == fake_result["fallback_chunks"]
    assert result["summary"] == (
        "Found 0 trails matching topic 'waterfalls'; returning 1 fallback semantic matches."
    )


def test_search_trails_empty_result_is_structured() -> None:
    fake_result = {
        "trail_count": 0,
        "total_miles": 0.0,
        "trails": [],
        "pagination": {"limit": 50, "offset": 0, "total_count": 0},
    }

    with patch("nps_hikes_mcp.tools.fetch_trails", return_value=fake_result):
        result = search_trails(park_code="yose", state="PA")

    assert result["trail_count"] == 0
    assert result["total_miles"] == 0.0
    assert result["trails"] == []
    assert "Found 0 trails totaling 0.0 miles" in result["summary"]


def test_search_parks_empty_result_is_structured() -> None:
    fake_result = {
        "park_count": 0,
        "visited_count": 0,
        "parks": [],
    }

    with patch("nps_hikes_mcp.tools.fetch_all_parks", return_value=fake_result):
        result = search_parks(state="ZZ")

    assert result["park_count"] == 0
    assert result["visited_count"] == 0
    assert result["parks"] == []
    assert result["summary"] == "Found 0 parks, including 0 visited parks."


def test_search_stats_zero_result_is_structured() -> None:
    fake_result = {
        "total_trails": 0,
        "total_miles": 0.0,
        "avg_trail_length": 0.0,
        "parks_count": 0,
        "states_count": 0,
        "source_breakdown": {"tnm": 0, "osm": 0},
        "longest_trail": None,
        "shortest_trail": None,
    }

    with patch("nps_hikes_mcp.tools.fetch_stats", return_value=fake_result):
        result = search_stats(hiked=True)

    assert result["total_trails"] == 0
    assert result["parks_count"] == 0
    assert (
        "Hiked trails include 0 trails across 0 parks and 0 states" in result["summary"]
    )


def test_search_park_summary_groups_fields() -> None:
    fake_result = {
        "park_code": "acad",
        "park_name": "Acadia",
        "full_name": "Acadia National Park",
        "designation": "National Park",
        "states": "ME",
        "latitude": 44.3386,
        "longitude": -68.2733,
        "url": "https://www.nps.gov/acad/index.htm",
        "visit_month": "October",
        "visit_year": 2024,
        "total_trails": 20,
        "total_miles": 45.6,
        "avg_trail_length": 2.28,
        "hiked_trails": 5,
        "hiked_miles": 12.3,
        "source_breakdown": {"tnm": 11, "osm": 9},
        "viz_3d_count": 2,
    }

    with patch("nps_hikes_mcp.tools.fetch_park_summary", return_value=fake_result):
        result = search_park_summary("acad")

    assert result["park"]["park_code"] == "acad"
    assert result["trail_stats"]["viz_3d_count"] == 2
    assert result["visit_info"]["visited"] is True
    assert result["source_breakdown"] == {"tnm": 11, "osm": 9}


def test_search_park_summary_raises_for_missing_park() -> None:
    with (
        patch("nps_hikes_mcp.tools.fetch_park_summary", return_value=None),
        pytest.raises(McpToolNotFoundError),
    ):
        search_park_summary("fake")


def test_search_trails_rejects_invalid_state() -> None:
    with pytest.raises(McpToolError, match="state must be a 2-letter uppercase code"):
        search_trails(state="California")


def test_search_trails_rejects_invalid_park_code() -> None:
    with pytest.raises(
        McpToolError, match="park_code must be a 4-letter lowercase code"
    ):
        search_trails(park_code="YOSE")


def test_search_parks_rejects_invalid_state() -> None:
    with pytest.raises(McpToolError, match="state must be a 2-letter uppercase code"):
        search_parks(state="California")


def test_search_stats_rejects_invalid_hiked_type() -> None:
    with pytest.raises(McpToolError, match="hiked must be a boolean value"):
        search_stats(hiked="yes")  # type: ignore[arg-type]


def test_search_by_topic_rejects_empty_query() -> None:
    with pytest.raises(McpToolError, match="query must be a non-empty string"):
        search_by_topic(query="   ")


def test_search_by_topic_rejects_large_limit() -> None:
    with pytest.raises(McpToolError, match="limit must be between 1 and 50"):
        search_by_topic(query="waterfalls", limit=51)


def test_search_trails_wraps_operational_errors() -> None:
    with (
        patch(
            "nps_hikes_mcp.tools.fetch_trails",
            side_effect=DatabaseError("database unavailable"),
        ),
        pytest.raises(McpToolError, match="search_trails failed: database unavailable"),
    ):
        search_trails(park_code="yose")


def test_search_parks_wraps_operational_errors() -> None:
    with (
        patch(
            "nps_hikes_mcp.tools.fetch_all_parks",
            side_effect=DatabaseError("database unavailable"),
        ),
        pytest.raises(McpToolError, match="search_parks failed: database unavailable"),
    ):
        search_parks(state="CA")


def test_search_stats_wraps_operational_errors() -> None:
    with (
        patch(
            "nps_hikes_mcp.tools.fetch_stats",
            side_effect=DatabaseError("database unavailable"),
        ),
        pytest.raises(McpToolError, match="search_stats failed: database unavailable"),
    ):
        search_stats()


def test_search_by_topic_wraps_embedding_errors() -> None:
    with (
        patch(
            "nps_hikes_mcp.tools.get_embeddings_sync",
            side_effect=LlmConnectionError("Cannot connect to Ollama"),
        ),
        pytest.raises(
            McpToolError,
            match="search_by_topic failed: embedding generation unavailable",
        ),
    ):
        search_by_topic(query="waterfalls")


def test_search_by_topic_rejects_empty_embedding_result() -> None:
    with (
        patch("nps_hikes_mcp.tools.get_embeddings_sync", return_value=[]),
        pytest.raises(
            McpToolError,
            match="embedding generation returned no usable vector",
        ),
    ):
        search_by_topic(query="waterfalls")


def test_search_by_topic_wraps_operational_errors() -> None:
    with (
        patch("nps_hikes_mcp.tools.get_embeddings_sync", return_value=[[0.01] * 768]),
        patch(
            "nps_hikes_mcp.tools.fetch_topic_trails",
            side_effect=DatabaseError("database unavailable"),
        ),
        pytest.raises(
            McpToolError,
            match="search_by_topic failed: database unavailable",
        ),
    ):
        search_by_topic(query="waterfalls")


def test_search_park_summary_wraps_operational_errors() -> None:
    with (
        patch(
            "nps_hikes_mcp.tools.fetch_park_summary",
            side_effect=DatabaseError("database unavailable"),
        ),
        pytest.raises(
            McpToolError,
            match="search_park_summary failed: database unavailable",
        ),
    ):
        search_park_summary("yose")


def test_read_resource_returns_expected_content() -> None:
    with patch(
        "nps_hikes_mcp.resources.get_park_lookup",
        return_value={
            "yose": "yose",
            "yosemite": "yose",
            "yosemite national park": "yose",
            "zion": "zion",
        },
    ):
        lookup_resource = get_park_lookup_resource()

    assert lookup_resource["park_count"] == 2
    assert lookup_resource["parks"][0]["primary_name"]
    assert "Trail provenance" in read_resource("search_methodology")


def test_read_resource_raises_for_unknown_uri() -> None:
    with pytest.raises(KeyError):
        read_resource("unknown")


def test_create_server_registers_tools_from_shared_definitions() -> None:
    class FakeFastMCP:
        def __init__(self, server_name: str) -> None:
            self.server_name = server_name
            self.registered_tools: list[dict[str, str]] = []
            self.resources: list[object] = []

        def tool(self, *, name: str, description: str):
            def decorator(fn):
                self.registered_tools.append(
                    {
                        "name": name,
                        "description": description,
                        "callable_name": fn.__name__,
                    }
                )
                return fn

            return decorator

        def add_resource(self, resource: object) -> None:
            self.resources.append(resource)

    class FakeFunctionResource:
        def __init__(
            self,
            *,
            uri: str,
            name: str,
            description: str,
            mime_type: str,
            fn,
        ) -> None:
            self.uri = uri
            self.name = name
            self.description = description
            self.mime_type = mime_type
            self.fn = fn

    with (
        patch.object(mcp_server, "_load_fastmcp", return_value=FakeFastMCP),
        patch.object(
            mcp_server,
            "_load_function_resource",
            return_value=FakeFunctionResource,
        ),
    ):
        app = mcp_server.create_server()

    assert app.server_name == "nps-hikes"
    assert app.registered_tools == [
        {
            "name": tool["name"],
            "description": tool["description"],
            "callable_name": tool["fn"].__name__,
        }
        for tool in TOOL_DEFINITIONS
    ]


def test_create_server_registers_resources_from_shared_definitions() -> None:
    class FakeFastMCP:
        def __init__(self, server_name: str) -> None:
            self.server_name = server_name
            self.registered_tools: list[dict[str, str]] = []
            self.resources: list[object] = []

        def tool(self, *, name: str, description: str):
            def decorator(fn):
                self.registered_tools.append(
                    {
                        "name": name,
                        "description": description,
                        "callable_name": fn.__name__,
                    }
                )
                return fn

            return decorator

        def add_resource(self, resource: object) -> None:
            self.resources.append(resource)

    class FakeFunctionResource:
        def __init__(
            self,
            *,
            uri: str,
            name: str,
            description: str,
            mime_type: str,
            fn,
        ) -> None:
            self.uri = uri
            self.name = name
            self.description = description
            self.mime_type = mime_type
            self.fn = fn

    with (
        patch.object(mcp_server, "_load_fastmcp", return_value=FakeFastMCP),
        patch.object(
            mcp_server,
            "_load_function_resource",
            return_value=FakeFunctionResource,
        ),
    ):
        app = mcp_server.create_server()

    assert [
        {
            "uri": resource.uri,
            "name": resource.name,
            "description": resource.description,
            "mime_type": resource.mime_type,
        }
        for resource in app.resources
    ] == [
        {
            "uri": f"resource://{resource['uri']}",
            "name": resource["name"],
            "description": resource["description"],
            "mime_type": resource["mime_type"],
        }
        for resource in RESOURCE_DEFINITIONS
    ]


def test_run_stdio_server_uses_default_run_method() -> None:
    class FakeFastMCP:
        def __init__(self) -> None:
            self.run_calls = 0

        def run(self) -> None:
            self.run_calls += 1

    app = FakeFastMCP()

    with patch.object(mcp_server, "create_server", return_value=app):
        mcp_server.run_stdio_server()

    assert app.run_calls == 1


def test_run_stdio_server_falls_back_to_run_stdio() -> None:
    class FakeFastMCP:
        def __init__(self) -> None:
            self.run_stdio_calls = 0

        run = None

        def run_stdio(self) -> None:
            self.run_stdio_calls += 1

    app = FakeFastMCP()

    with patch.object(mcp_server, "create_server", return_value=app):
        mcp_server.run_stdio_server()

    assert app.run_stdio_calls == 1


def test_run_http_server_uses_streamable_http_defaults() -> None:
    class FakeFastMCP:
        def __init__(self) -> None:
            self.run_kwargs: dict[str, object] | None = None

        def run(self, **kwargs: object) -> None:
            self.run_kwargs = kwargs

    app = FakeFastMCP()

    with patch.object(mcp_server, "create_server", return_value=app):
        mcp_server.run_http_server()

    assert app.run_kwargs == {
        "transport": "streamable-http",
        "host": mcp_server.DEFAULT_HTTP_HOST,
        "port": mcp_server.DEFAULT_HTTP_PORT,
        "path": mcp_server.DEFAULT_HTTP_PATH,
        "log_level": None,
    }


def test_run_http_server_supports_explicit_overrides() -> None:
    class FakeFastMCP:
        def __init__(self) -> None:
            self.run_kwargs: dict[str, object] | None = None

        def run(self, **kwargs: object) -> None:
            self.run_kwargs = kwargs

    app = FakeFastMCP()

    with patch.object(mcp_server, "create_server", return_value=app):
        mcp_server.run_http_server(
            host="localhost",
            port=9100,
            path="/custom-mcp",
            log_level="warning",
        )

    assert app.run_kwargs == {
        "transport": "streamable-http",
        "host": "localhost",
        "port": 9100,
        "path": "/custom-mcp",
        "log_level": "warning",
    }


def test_http_server_main_parses_and_forwards_arguments() -> None:
    with patch.object(http_server, "run_http_server") as mock_run_http:
        http_server.main(
            [
                "--host",
                "localhost",
                "--port",
                "9100",
                "--path",
                "/custom-mcp",
                "--log-level",
                "info",
            ]
        )

    mock_run_http.assert_called_once_with(
        host="localhost",
        port=9100,
        path="/custom-mcp",
        log_level="info",
    )

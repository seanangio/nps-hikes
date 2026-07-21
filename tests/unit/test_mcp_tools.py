"""Unit tests for MCP tool and resource wrappers."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from nps_hikes_mcp.resources import get_park_lookup_resource, read_resource
from nps_hikes_mcp.tools import (
    McpToolError,
    McpToolNotFoundError,
    search_park_summary,
    search_parks,
    search_stats,
    search_trails,
)
from utils.exceptions import DatabaseError


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

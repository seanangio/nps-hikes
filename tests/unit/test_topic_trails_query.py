"""
Tests for the fetch_topic_trails query function.

Tests semantic search → content_trail_mapping JOIN → trail data output,
including deduplication, filtering, fallback chunks, and topic context.
"""

from collections import namedtuple
from unittest.mock import Mock, patch

import pytest

from api.queries import fetch_topic_trails

# Row shape for trail query results (with geojson)
TrailRow = namedtuple(
    "TrailRow",
    [
        "trail_id",
        "trail_name",
        "park_code",
        "park_name",
        "states",
        "source",
        "length_miles",
        "geometry_type",
        "highway_type",
        "content_title",
        "chunk_text",
        "similarity_score",
        "hiked",
        "viz_3d_available",
        "viz_3d_slug",
        "geojson",
    ],
)

# Row shape for trail query results (without geojson)
TrailRowNoGeo = namedtuple(
    "TrailRowNoGeo",
    [
        "trail_id",
        "trail_name",
        "park_code",
        "park_name",
        "states",
        "source",
        "length_miles",
        "geometry_type",
        "highway_type",
        "content_title",
        "chunk_text",
        "similarity_score",
        "hiked",
        "viz_3d_available",
        "viz_3d_slug",
    ],
)

# Row shape for fallback query results
FallbackRow = namedtuple(
    "FallbackRow",
    [
        "title",
        "chunk_text",
        "park_code",
        "park_name",
        "source_type",
        "similarity_score",
    ],
)

SAMPLE_EMBEDDING = [0.01] * 768


def _make_trail_row(
    trail_id="550779",
    trail_name="Mist Trail",
    park_code="yose",
    park_name="Yosemite National Park",
    states="CA",
    source="TNM",
    length_miles=5.4,
    geometry_type="LineString",
    highway_type=None,
    content_title="Hike to Vernal Fall",
    chunk_text="Follow the Mist Trail to see the 317-foot waterfall.",
    similarity_score=0.92,
    hiked=True,
    viz_3d_available=False,
    viz_3d_slug=None,
    geojson='{"type": "LineString", "coordinates": [[-119.5, 37.7]]}',
):
    """Helper to create a TrailRow with sensible defaults."""
    return TrailRow(
        trail_id=trail_id,
        trail_name=trail_name,
        park_code=park_code,
        park_name=park_name,
        states=states,
        source=source,
        length_miles=length_miles,
        geometry_type=geometry_type,
        highway_type=highway_type,
        content_title=content_title,
        chunk_text=chunk_text,
        similarity_score=similarity_score,
        hiked=hiked,
        viz_3d_available=viz_3d_available,
        viz_3d_slug=viz_3d_slug,
        geojson=geojson,
    )


def _make_trail_row_no_geo(**kwargs):
    """Helper to create a TrailRowNoGeo with sensible defaults."""
    defaults = dict(
        trail_id="550779",
        trail_name="Mist Trail",
        park_code="yose",
        park_name="Yosemite National Park",
        states="CA",
        source="TNM",
        length_miles=5.4,
        geometry_type="LineString",
        highway_type=None,
        content_title="Hike to Vernal Fall",
        chunk_text="Follow the Mist Trail to see the 317-foot waterfall.",
        similarity_score=0.92,
        hiked=True,
        viz_3d_available=False,
        viz_3d_slug=None,
    )
    defaults.update(kwargs)
    return TrailRowNoGeo(**defaults)


def _setup_mock_engine(mock_get_engine, trail_rows, fallback_rows=None):
    """
    Configure mock engine for fetch_topic_trails.

    When fallback_rows is provided, the mock supports two consecutive
    execute() calls (trail query then fallback query). Otherwise only
    the trail query is mocked.
    """
    from unittest.mock import MagicMock

    mock_engine = MagicMock()
    mock_get_engine.return_value = mock_engine

    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn

    if fallback_rows is not None:
        # Two queries: trail query (empty) then fallback query
        trail_result = Mock()
        trail_result.fetchall.return_value = trail_rows

        fallback_result = Mock()
        fallback_result.fetchall.return_value = fallback_rows

        mock_conn.execute.side_effect = [trail_result, fallback_result]
    else:
        # Single query: trail query only
        mock_result = Mock()
        mock_result.fetchall.return_value = trail_rows
        mock_conn.execute.return_value = mock_result

    return mock_engine, mock_conn


class TestFetchTopicTrailsBasic:
    """Basic trail result tests."""

    @patch("api.queries.get_db_engine")
    def test_returns_trail_data_matching_fetch_trails_shape(self, mock_get_engine):
        """Trail dicts should match the shape returned by fetch_trails."""
        row = _make_trail_row()
        _setup_mock_engine(mock_get_engine, [row])

        result = fetch_topic_trails(query_embedding=SAMPLE_EMBEDDING)

        assert result["trail_count"] == 1
        assert result["total_miles"] == 5.4

        trail = result["trails"][0]
        assert trail["trail_id"] == "550779"
        assert trail["trail_name"] == "Mist Trail"
        assert trail["park_code"] == "yose"
        assert trail["park_name"] == "Yosemite National Park"
        assert trail["states"] == "CA"
        assert trail["source"] == "TNM"
        assert trail["length_miles"] == 5.4
        assert trail["geometry_type"] == "LineString"
        assert trail["highway_type"] is None
        assert trail["hiked"] is True
        assert trail["viz_3d_available"] is False
        assert trail["viz_3d_slug"] is None
        assert "geometry" in trail

    @patch("api.queries.get_db_engine")
    def test_multiple_trails(self, mock_get_engine):
        """Multiple distinct trails should all appear in results."""
        rows = [
            _make_trail_row(
                trail_id="111",
                trail_name="Mist Trail",
                length_miles=5.4,
                similarity_score=0.95,
            ),
            _make_trail_row(
                trail_id="222",
                trail_name="Half Dome Trail",
                length_miles=14.2,
                source="TNM",
                similarity_score=0.88,
            ),
        ]
        _setup_mock_engine(mock_get_engine, rows)

        result = fetch_topic_trails(query_embedding=SAMPLE_EMBEDDING)

        assert result["trail_count"] == 2
        assert result["total_miles"] == 19.6
        names = {t["trail_name"] for t in result["trails"]}
        assert names == {"Mist Trail", "Half Dome Trail"}

    @patch("api.queries.get_db_engine")
    def test_osm_trail_included(self, mock_get_engine):
        """OSM trails should be included with highway_type."""
        row = _make_trail_row(
            trail_id="987654",
            source="OSM",
            highway_type="path",
        )
        _setup_mock_engine(mock_get_engine, [row])

        result = fetch_topic_trails(query_embedding=SAMPLE_EMBEDDING)

        trail = result["trails"][0]
        assert trail["source"] == "OSM"
        assert trail["highway_type"] == "path"

    @patch("api.queries.get_db_engine")
    def test_total_miles_rounded(self, mock_get_engine):
        """Total miles should be rounded to 2 decimal places."""
        rows = [
            _make_trail_row(trail_id="1", length_miles=3.333),
            _make_trail_row(trail_id="2", length_miles=2.777),
        ]
        _setup_mock_engine(mock_get_engine, rows)

        result = fetch_topic_trails(query_embedding=SAMPLE_EMBEDDING)

        assert result["total_miles"] == 6.11


class TestFetchTopicTrailsGeojson:
    """GeoJSON geometry handling."""

    @patch("api.queries.get_db_engine")
    def test_geojson_included_by_default(self, mock_get_engine):
        """Geometry should be included when geojson=True (default)."""
        row = _make_trail_row(
            geojson='{"type": "LineString", "coordinates": [[-119.5, 37.7]]}'
        )
        _setup_mock_engine(mock_get_engine, [row])

        result = fetch_topic_trails(query_embedding=SAMPLE_EMBEDDING)

        trail = result["trails"][0]
        assert "geometry" in trail
        assert trail["geometry"]["type"] == "LineString"

    @patch("api.queries.get_db_engine")
    def test_geojson_null_geometry(self, mock_get_engine):
        """Null geometry should become None."""
        row = _make_trail_row(geojson=None)
        _setup_mock_engine(mock_get_engine, [row])

        result = fetch_topic_trails(query_embedding=SAMPLE_EMBEDDING)

        assert result["trails"][0]["geometry"] is None

    @patch("api.queries.get_db_engine")
    def test_geojson_excluded(self, mock_get_engine):
        """Geometry should not be included when geojson=False."""
        row = _make_trail_row_no_geo()
        _setup_mock_engine(mock_get_engine, [row])

        result = fetch_topic_trails(query_embedding=SAMPLE_EMBEDDING, geojson=False)

        assert "geometry" not in result["trails"][0]


class TestFetchTopicTrailsDeduplication:
    """Trail deduplication across content chunks."""

    @patch("api.queries.get_db_engine")
    def test_same_trail_multiple_chunks_deduped(self, mock_get_engine):
        """Same trail matched by multiple content should appear once."""
        rows = [
            _make_trail_row(
                trail_id="550779",
                trail_name="Mist Trail",
                content_title="Hike to Vernal Fall",
                similarity_score=0.95,
            ),
            _make_trail_row(
                trail_id="550779",
                trail_name="Mist Trail",
                content_title="Mist Trail Overview",
                similarity_score=0.88,
            ),
        ]
        _setup_mock_engine(mock_get_engine, rows)

        result = fetch_topic_trails(query_embedding=SAMPLE_EMBEDDING)

        assert result["trail_count"] == 1
        assert result["trails"][0]["trail_id"] == "550779"

    @patch("api.queries.get_db_engine")
    def test_dedup_keeps_highest_similarity(self, mock_get_engine):
        """Deduplication should keep the first (highest similarity) entry."""
        rows = [
            _make_trail_row(
                trail_id="550779",
                content_title="Best match",
                similarity_score=0.95,
                length_miles=5.4,
            ),
            _make_trail_row(
                trail_id="550779",
                content_title="Second match",
                similarity_score=0.80,
                length_miles=5.4,
            ),
        ]
        _setup_mock_engine(mock_get_engine, rows)

        result = fetch_topic_trails(query_embedding=SAMPLE_EMBEDDING)

        # Trail data comes from first row (highest similarity due to ORDER BY)
        assert result["trail_count"] == 1
        assert result["total_miles"] == 5.4

    @patch("api.queries.get_db_engine")
    def test_different_trail_ids_not_deduped(self, mock_get_engine):
        """Trails with different IDs should not be deduplicated."""
        rows = [
            _make_trail_row(trail_id="111", trail_name="Trail A"),
            _make_trail_row(trail_id="222", trail_name="Trail B"),
        ]
        _setup_mock_engine(mock_get_engine, rows)

        result = fetch_topic_trails(query_embedding=SAMPLE_EMBEDDING)

        assert result["trail_count"] == 2


class TestFetchTopicTrailsTopicContext:
    """Topic context collection."""

    @patch("api.queries.get_db_engine")
    def test_topic_context_populated(self, mock_get_engine):
        """Topic context should contain content info for each match."""
        row = _make_trail_row(
            content_title="Hike to Vernal Fall",
            chunk_text="Follow the Mist Trail to see the waterfall.",
        )
        _setup_mock_engine(mock_get_engine, [row])

        result = fetch_topic_trails(query_embedding=SAMPLE_EMBEDDING)

        assert len(result["topic_context"]) == 1
        ctx = result["topic_context"][0]
        assert ctx["trail_id"] == "550779"
        assert ctx["trail_name"] == "Mist Trail"
        assert ctx["content_title"] == "Hike to Vernal Fall"
        assert "waterfall" in ctx["chunk_text_preview"]
        assert ctx["park_code"] == "yose"
        assert ctx["park_name"] == "Yosemite National Park"
        assert ctx["chunk_text"] == "Follow the Mist Trail to see the waterfall."

    @patch("api.queries.get_db_engine")
    def test_topic_context_multiple_chunks_per_trail(self, mock_get_engine):
        """Multiple content chunks for same trail create multiple context entries."""
        rows = [
            _make_trail_row(
                trail_id="550779",
                content_title="Hike to Vernal Fall",
                similarity_score=0.95,
            ),
            _make_trail_row(
                trail_id="550779",
                content_title="Mist Trail Overview",
                similarity_score=0.88,
            ),
        ]
        _setup_mock_engine(mock_get_engine, rows)

        result = fetch_topic_trails(query_embedding=SAMPLE_EMBEDDING)

        # One trail but two context entries
        assert result["trail_count"] == 1
        assert len(result["topic_context"]) == 2
        titles = {ctx["content_title"] for ctx in result["topic_context"]}
        assert titles == {"Hike to Vernal Fall", "Mist Trail Overview"}

    @patch("api.queries.get_db_engine")
    def test_chunk_text_preview_truncated(self, mock_get_engine):
        """Chunk text preview should be truncated to 200 characters."""
        long_text = "A" * 500
        row = _make_trail_row(chunk_text=long_text)
        _setup_mock_engine(mock_get_engine, [row])

        result = fetch_topic_trails(query_embedding=SAMPLE_EMBEDDING)

        preview = result["topic_context"][0]["chunk_text_preview"]
        assert len(preview) == 200

    @patch("api.queries.get_db_engine")
    def test_chunk_text_preview_none_for_null(self, mock_get_engine):
        """Null chunk text should produce None preview."""
        row = _make_trail_row(chunk_text=None)
        _setup_mock_engine(mock_get_engine, [row])

        result = fetch_topic_trails(query_embedding=SAMPLE_EMBEDDING)

        assert result["topic_context"][0]["chunk_text_preview"] is None

    @patch("api.queries.get_db_engine")
    def test_topic_context_includes_park_and_full_text(self, mock_get_engine):
        """Topic context should include park_code, park_name, and full chunk_text."""
        long_text = "A" * 500
        row = _make_trail_row(
            park_code="zion",
            park_name="Zion National Park",
            chunk_text=long_text,
        )
        _setup_mock_engine(mock_get_engine, [row])

        result = fetch_topic_trails(query_embedding=SAMPLE_EMBEDDING)

        ctx = result["topic_context"][0]
        assert ctx["park_code"] == "zion"
        assert ctx["park_name"] == "Zion National Park"
        # chunk_text is the full text, chunk_text_preview is truncated
        assert len(ctx["chunk_text"]) == 500
        assert len(ctx["chunk_text_preview"]) == 200


class TestFetchTopicTrailsLimit:
    """Limit and pagination behavior."""

    @patch("api.queries.get_db_engine")
    def test_limit_applied(self, mock_get_engine):
        """Results should respect the limit parameter."""
        rows = [
            _make_trail_row(
                trail_id=str(i),
                trail_name=f"Trail {i}",
                length_miles=float(i),
            )
            for i in range(5)
        ]
        _setup_mock_engine(mock_get_engine, rows)

        result = fetch_topic_trails(query_embedding=SAMPLE_EMBEDDING, limit=3)

        assert result["trail_count"] == 3
        assert len(result["trails"]) == 3

    @patch("api.queries.get_db_engine")
    def test_total_miles_matches_limited_trails(self, mock_get_engine):
        """Total miles should only count trails within the limit."""
        rows = [_make_trail_row(trail_id=str(i), length_miles=10.0) for i in range(5)]
        _setup_mock_engine(mock_get_engine, rows)

        result = fetch_topic_trails(query_embedding=SAMPLE_EMBEDDING, limit=2)

        assert result["total_miles"] == 20.0

    @patch("api.queries.get_db_engine")
    def test_topic_context_filtered_by_limit(self, mock_get_engine):
        """Topic context should only include entries for limited trails."""
        rows = [
            _make_trail_row(
                trail_id=str(i),
                trail_name=f"Trail {i}",
                content_title=f"Content {i}",
            )
            for i in range(5)
        ]
        _setup_mock_engine(mock_get_engine, rows)

        result = fetch_topic_trails(query_embedding=SAMPLE_EMBEDDING, limit=2)

        # Topic context should only have entries for the 2 limited trails
        context_trail_ids = {tc["trail_id"] for tc in result["topic_context"]}
        result_trail_ids = {t["trail_id"] for t in result["trails"]}
        assert context_trail_ids == result_trail_ids


class TestFetchTopicTrailsEmptyResults:
    """Empty result handling."""

    @patch("api.queries.get_db_engine")
    def test_no_semantic_matches(self, mock_get_engine):
        """Empty semantic search should return zero trails."""
        _setup_mock_engine(mock_get_engine, [], fallback_rows=[])

        result = fetch_topic_trails(query_embedding=SAMPLE_EMBEDDING)

        assert result["trail_count"] == 0
        assert result["total_miles"] == 0.0
        assert result["trails"] == []
        assert result["topic_context"] == []
        assert result["fallback_chunks"] == []


class TestFetchTopicTrailsFallback:
    """Fallback chunk behavior."""

    @patch("api.queries.get_db_engine")
    def test_fallback_populated_when_no_trails(self, mock_get_engine):
        """When no trails match, fallback chunks should be populated."""
        fallback_rows = [
            FallbackRow(
                title="Best Time to Visit",
                chunk_text="Spring is the best time to visit Yosemite.",
                park_code="yose",
                park_name="Yosemite National Park",
                source_type="thingstodo",
                similarity_score=0.85,
            ),
            FallbackRow(
                title="Winter Activities",
                chunk_text="Try snowshoeing and cross-country skiing.",
                park_code="yose",
                park_name="Yosemite National Park",
                source_type="thingstodo",
                similarity_score=0.78,
            ),
        ]
        _setup_mock_engine(mock_get_engine, trail_rows=[], fallback_rows=fallback_rows)

        result = fetch_topic_trails(query_embedding=SAMPLE_EMBEDDING)

        assert result["trail_count"] == 0
        assert len(result["fallback_chunks"]) == 2

        chunk = result["fallback_chunks"][0]
        assert chunk["title"] == "Best Time to Visit"
        assert "Spring" in chunk["chunk_text"]
        assert chunk["park_code"] == "yose"
        assert chunk["park_name"] == "Yosemite National Park"
        assert chunk["source_type"] == "thingstodo"
        assert chunk["similarity_score"] == 0.85

    @patch("api.queries.get_db_engine")
    def test_fallback_empty_when_trails_exist(self, mock_get_engine):
        """When trails match, fallback should be empty (not queried)."""
        row = _make_trail_row()
        _setup_mock_engine(mock_get_engine, [row])

        result = fetch_topic_trails(query_embedding=SAMPLE_EMBEDDING)

        assert result["trail_count"] == 1
        assert result["fallback_chunks"] == []

    @patch("api.queries.get_db_engine")
    def test_fallback_similarity_score_rounded(self, mock_get_engine):
        """Fallback similarity scores should be rounded to 4 decimals."""
        fallback_rows = [
            FallbackRow(
                title="Test",
                chunk_text="Test chunk",
                park_code="yose",
                park_name="Yosemite National Park",
                source_type="thingstodo",
                similarity_score=0.856789,
            ),
        ]
        _setup_mock_engine(mock_get_engine, trail_rows=[], fallback_rows=fallback_rows)

        result = fetch_topic_trails(query_embedding=SAMPLE_EMBEDDING)

        assert result["fallback_chunks"][0]["similarity_score"] == 0.8568


class TestFetchTopicTrailsFilters:
    """Park code and state filter tests."""

    @patch("api.queries.get_db_engine")
    def test_park_code_filter_passed_to_query(self, mock_get_engine):
        """park_code filter should be included in query params."""
        _mock_engine, mock_conn = _setup_mock_engine(mock_get_engine, [])
        # Need fallback since trail_rows is empty
        fallback_result = Mock()
        fallback_result.fetchall.return_value = []
        mock_conn.execute.side_effect = [
            mock_conn.execute.return_value,
            fallback_result,
        ]

        fetch_topic_trails(query_embedding=SAMPLE_EMBEDDING, park_code="yose")

        # Verify execute was called with park_code in params
        call_args = mock_conn.execute.call_args_list[0]
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
        assert params["park_code"] == "yose"

    @patch("api.queries.get_db_engine")
    def test_state_filter_passed_to_query(self, mock_get_engine):
        """state filter should be formatted with wildcards."""
        _mock_engine, mock_conn = _setup_mock_engine(mock_get_engine, [])
        fallback_result = Mock()
        fallback_result.fetchall.return_value = []
        mock_conn.execute.side_effect = [
            mock_conn.execute.return_value,
            fallback_result,
        ]

        fetch_topic_trails(query_embedding=SAMPLE_EMBEDDING, state="CA")

        call_args = mock_conn.execute.call_args_list[0]
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
        assert params["state"] == "%CA%"

    @patch("api.queries.get_db_engine")
    def test_park_code_with_trail_results(self, mock_get_engine):
        """Park code filter should work with actual trail results."""
        row = _make_trail_row(park_code="yose")
        _setup_mock_engine(mock_get_engine, [row])

        result = fetch_topic_trails(query_embedding=SAMPLE_EMBEDDING, park_code="yose")

        assert result["trail_count"] == 1
        assert result["trails"][0]["park_code"] == "yose"

    @patch("api.queries.get_db_engine")
    def test_state_with_trail_results(self, mock_get_engine):
        """State filter should work with actual trail results."""
        row = _make_trail_row(states="CA")
        _setup_mock_engine(mock_get_engine, [row])

        result = fetch_topic_trails(query_embedding=SAMPLE_EMBEDDING, state="CA")

        assert result["trail_count"] == 1
        assert result["trails"][0]["states"] == "CA"


class TestFetchTopicTrailsReturnStructure:
    """Verify the complete return structure."""

    @patch("api.queries.get_db_engine")
    def test_all_keys_present(self, mock_get_engine):
        """Return dict should have all expected keys."""
        row = _make_trail_row()
        _setup_mock_engine(mock_get_engine, [row])

        result = fetch_topic_trails(query_embedding=SAMPLE_EMBEDDING)

        assert "trail_count" in result
        assert "total_miles" in result
        assert "trails" in result
        assert "topic_context" in result
        assert "fallback_chunks" in result

    @patch("api.queries.get_db_engine")
    def test_all_keys_present_empty(self, mock_get_engine):
        """Return dict should have all keys even with no results."""
        _setup_mock_engine(mock_get_engine, [], fallback_rows=[])

        result = fetch_topic_trails(query_embedding=SAMPLE_EMBEDDING)

        assert "trail_count" in result
        assert "total_miles" in result
        assert "trails" in result
        assert "topic_context" in result
        assert "fallback_chunks" in result

    @patch("api.queries.get_db_engine")
    def test_viz_3d_fields_included(self, mock_get_engine):
        """Trail data should include viz_3d fields."""
        row = _make_trail_row(viz_3d_available=True, viz_3d_slug="mist_trail")
        _setup_mock_engine(mock_get_engine, [row])

        result = fetch_topic_trails(query_embedding=SAMPLE_EMBEDDING)

        trail = result["trails"][0]
        assert trail["viz_3d_available"] is True
        assert trail["viz_3d_slug"] == "mist_trail"

    @patch("api.queries.get_db_engine")
    def test_hiked_status_included(self, mock_get_engine):
        """Trail data should include hiked status."""
        rows = [
            _make_trail_row(trail_id="1", hiked=True),
            _make_trail_row(trail_id="2", hiked=False),
        ]
        _setup_mock_engine(mock_get_engine, rows)

        result = fetch_topic_trails(query_embedding=SAMPLE_EMBEDDING)

        hiked_values = {t["trail_id"]: t["hiked"] for t in result["trails"]}
        assert hiked_values["1"] is True
        assert hiked_values["2"] is False

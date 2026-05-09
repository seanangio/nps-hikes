"""Unit tests for the NPS content collector."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from scripts.collectors.nps_content_collector import NPSContentCollector


class TestNPSContentCollector:
    """Tests for NPSContentCollector."""

    def test_init_with_api_key(self, test_api_key):
        collector = NPSContentCollector(api_key=test_api_key)
        assert collector.api_key == test_api_key
        assert collector.db_writer is None

    def test_init_uses_config_api_key(self):
        collector = NPSContentCollector()
        assert collector.api_key is not None

    def test_fetch_thingstodo_for_park_success(
        self, content_collector, sample_thingstodo_api_response
    ):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total": "1",
            "data": [sample_thingstodo_api_response],
        }
        mock_response.headers = {"X-RateLimit-Remaining": "100"}
        mock_response.raise_for_status.return_value = None

        with patch.object(content_collector.session, "get", return_value=mock_response):
            results = content_collector.fetch_thingstodo_for_park("yose")

        assert len(results) == 1
        assert results[0]["title"] == "Hike to Vernal Fall"
        assert results[0]["park_code"] == "yose"

    def test_fetch_places_for_park_success(
        self, content_collector, sample_places_api_response
    ):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total": "1",
            "data": [sample_places_api_response],
        }
        mock_response.headers = {"X-RateLimit-Remaining": "100"}
        mock_response.raise_for_status.return_value = None

        with patch.object(content_collector.session, "get", return_value=mock_response):
            results = content_collector.fetch_places_for_park("yose")

        assert len(results) == 1
        assert results[0]["title"] == "Glacier Point"
        assert results[0]["park_code"] == "yose"

    def test_fetch_thingstodo_pagination(
        self, content_collector, sample_thingstodo_api_response
    ):
        page1_response = Mock()
        page1_response.status_code = 200
        page1_response.json.return_value = {
            "total": "2",
            "data": [sample_thingstodo_api_response],
        }
        page1_response.headers = {}
        page1_response.raise_for_status.return_value = None

        item2 = dict(sample_thingstodo_api_response)
        item2["id"] = "XYZ789"
        item2["title"] = "Star Gazing"

        page2_response = Mock()
        page2_response.status_code = 200
        page2_response.json.return_value = {
            "total": "2",
            "data": [item2],
        }
        page2_response.headers = {}
        page2_response.raise_for_status.return_value = None

        with patch.object(
            content_collector.session,
            "get",
            side_effect=[page1_response, page2_response],
        ):
            # Use page_size=1 to force pagination
            from config.settings import config

            original_page_size = config.NPS_CONTENT_PAGE_SIZE
            config.NPS_CONTENT_PAGE_SIZE = 1
            try:
                results = content_collector.fetch_thingstodo_for_park("yose")
            finally:
                config.NPS_CONTENT_PAGE_SIZE = original_page_size

        assert len(results) == 2

    def test_api_timeout_returns_empty(self, content_collector):
        import requests

        with patch.object(
            content_collector.session,
            "get",
            side_effect=requests.exceptions.Timeout("timeout"),
        ):
            results = content_collector.fetch_thingstodo_for_park("yose")

        assert results == []

    def test_api_500_error_returns_empty(self, content_collector):
        import requests

        error_response = Mock()
        error_response.status_code = 500

        with patch.object(
            content_collector.session,
            "get",
            side_effect=requests.exceptions.HTTPError(response=error_response),
        ):
            results = content_collector.fetch_thingstodo_for_park("yose")

        assert results == []

    def test_api_404_error_returns_empty(self, content_collector):
        import requests

        error_response = Mock()
        error_response.status_code = 404

        with patch.object(
            content_collector.session,
            "get",
            side_effect=requests.exceptions.HTTPError(response=error_response),
        ):
            results = content_collector.fetch_thingstodo_for_park("yose")

        assert results == []

    def test_empty_response_handled(self, content_collector):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"total": "0", "data": []}
        mock_response.headers = {}
        mock_response.raise_for_status.return_value = None

        with patch.object(content_collector.session, "get", return_value=mock_response):
            results = content_collector.fetch_thingstodo_for_park("yose")

        assert results == []

    def test_html_stripped_in_results(
        self, content_collector, sample_thingstodo_api_response
    ):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total": "1",
            "data": [sample_thingstodo_api_response],
        }
        mock_response.headers = {}
        mock_response.raise_for_status.return_value = None

        with patch.object(content_collector.session, "get", return_value=mock_response):
            results = content_collector.fetch_thingstodo_for_park("yose")

        assert "<b>" not in (results[0].get("short_description") or "")

    def test_get_park_codes_requires_db(self, content_collector):
        from utils.exceptions import ApiRequestError

        with pytest.raises(ApiRequestError):
            content_collector.get_park_codes_from_db()

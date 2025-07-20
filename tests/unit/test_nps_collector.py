import pytest
import pandas as pd
from unittest.mock import Mock, patch


class TestNPSDataCollector:

    def test_validate_coordinates_valid_input(self, collector):
        """Test coordinate validation with valid inputs."""
        lat, lon = collector._validate_coordinates("36.1085", "-115.1777", "Test Park")
        assert lat == 36.1085
        assert lon == -115.1777

    def test_validate_coordinates_invalid_latitude(self, collector):
        """Test coordinate validation with invalid latitude."""
        lat, lon = collector._validate_coordinates("91", "-115.1777", "Test Park")
        assert lat is None
        assert lon is None

    def test_validate_coordinates_invalid_format(self, collector):
        """Test coordinate validation with non-numeric input."""
        lat, lon = collector._validate_coordinates(
            "not_a_number", "-115.1777", "Test Park"
        )
        assert lat is None
        assert lon is None

    def test_find_best_park_match_exact_match(self, collector):
        """Test park matching with exact fullName match."""
        mock_results = [
            {
                "fullName": "Zion National Park",
                "parkCode": "zion",
                "relevanceScore": 80,
            },
            {"fullName": "Other Park", "parkCode": "other", "relevanceScore": 100},
        ]

        match = collector._find_best_park_match(
            mock_results, "Zion National Park", "Zion"
        )

        assert match["parkCode"] == "zion"
        assert match["fullName"] == "Zion National Park"

    def test_find_best_park_match_relevance_fallback(self, collector):
        """Test park matching falls back to highest relevance when no exact match."""
        mock_results = [
            {"fullName": "Some Other Park", "parkCode": "other", "relevanceScore": 100},
            {
                "fullName": "Lower Relevance Park",
                "parkCode": "lower",
                "relevanceScore": 80,
            },
        ]

        match = collector._find_best_park_match(
            mock_results, "Nonexistent Park", "Nonexistent"
        )

        # Should pick the first one (highest relevance due to pre-sorting)
        assert match["parkCode"] == "other"
        assert match["relevanceScore"] == 100

    def test_extract_park_data_complete_data(self, collector, sample_csv_row):
        """Test data extraction with complete API response."""
        mock_api_data = {
            "parkCode": "zion",
            "fullName": "Zion National Park",
            "states": "UT",
            "url": "https://www.nps.gov/zion/",
            "latitude": "37.2982022",
            "longitude": "-113.026505",
            "description": "Test description",
        }

        result = collector.extract_park_data(mock_api_data, sample_csv_row)

        assert result["park_name"] == "Zion"
        assert result["visit_month"] == "June"
        assert result["visit_year"] == 2024
        assert result["park_code"] == "zion"
        assert result["full_name"] == "Zion National Park"
        assert result["latitude"] == 37.2982022
        assert result["longitude"] == -113.026505

    def test_extract_park_data_missing_coordinates(self, collector, sample_csv_row):
        """Test data extraction when coordinates are missing."""
        mock_api_data = {
            "parkCode": "test",
            "fullName": "Test Park",
            "states": "UT",
            "url": "https://test.com",
            "description": "Test description",
            # No latitude/longitude
        }

        result = collector.extract_park_data(mock_api_data, sample_csv_row)

        assert result["latitude"] is None
        assert result["longitude"] is None
        assert result["park_code"] == "test"  # Other fields should still work

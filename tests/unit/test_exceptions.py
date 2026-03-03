"""
Unit tests for utils.exceptions module.

Tests cover the exception hierarchy, context attribute, chaining, and string representation.
"""

import pytest

from utils.exceptions import (
    ApiRequestError,
    ApiResponseError,
    CollectorError,
    ConfigurationError,
    DatabaseConnectionError,
    DatabaseError,
    DatabaseWriteError,
    DataProcessingError,
    NpsHikesError,
    SchemaValidationError,
)


class TestExceptionHierarchy:
    """Verify each exception is a subclass of its expected parent."""

    def test_base_inherits_from_exception(self):
        assert issubclass(NpsHikesError, Exception)

    def test_configuration_error_hierarchy(self):
        assert issubclass(ConfigurationError, NpsHikesError)
        assert issubclass(ConfigurationError, Exception)

    def test_collector_error_hierarchy(self):
        assert issubclass(CollectorError, NpsHikesError)

    def test_api_request_error_hierarchy(self):
        assert issubclass(ApiRequestError, CollectorError)
        assert issubclass(ApiRequestError, NpsHikesError)

    def test_api_response_error_hierarchy(self):
        assert issubclass(ApiResponseError, CollectorError)
        assert issubclass(ApiResponseError, NpsHikesError)

    def test_schema_validation_error_hierarchy(self):
        assert issubclass(SchemaValidationError, CollectorError)
        assert issubclass(SchemaValidationError, NpsHikesError)

    def test_database_error_hierarchy(self):
        assert issubclass(DatabaseError, NpsHikesError)

    def test_database_connection_error_hierarchy(self):
        assert issubclass(DatabaseConnectionError, DatabaseError)
        assert issubclass(DatabaseConnectionError, NpsHikesError)

    def test_database_write_error_hierarchy(self):
        assert issubclass(DatabaseWriteError, DatabaseError)
        assert issubclass(DatabaseWriteError, NpsHikesError)

    def test_data_processing_error_hierarchy(self):
        assert issubclass(DataProcessingError, NpsHikesError)


class TestExceptionContext:
    """Verify context attribute stores and retrieves structured data."""

    def test_default_context_is_empty_dict(self):
        err = NpsHikesError("test")
        assert err.context == {}

    def test_context_stores_data(self):
        ctx = {"park_code": "yose", "table": "osm_hikes"}
        err = NpsHikesError("test", context=ctx)
        assert err.context == ctx
        assert err.context["park_code"] == "yose"

    def test_context_on_subclass(self):
        ctx = {"endpoint": "/parks", "status_code": 503}
        err = DatabaseConnectionError("connection refused", context=ctx)
        assert err.context["endpoint"] == "/parks"
        assert err.context["status_code"] == 503

    def test_none_context_becomes_empty_dict(self):
        err = ApiRequestError("timeout", context=None)
        assert err.context == {}


class TestExceptionChaining:
    """Verify raise ... from e preserves __cause__."""

    def test_from_chaining_preserves_cause(self):
        original = ValueError("original error")
        try:
            try:
                raise original
            except ValueError as e:
                raise DatabaseWriteError("write failed") from e
        except DatabaseWriteError as exc:
            assert exc.__cause__ is original
            assert str(exc) == "write failed"

    def test_chaining_with_requests_exception(self):
        """Simulate wrapping a requests exception."""
        original = ConnectionError("connection refused")
        try:
            try:
                raise original
            except ConnectionError as e:
                raise ApiRequestError(
                    "API call failed", context={"url": "https://api.example.com"}
                ) from e
        except ApiRequestError as exc:
            assert exc.__cause__ is original
            assert exc.context["url"] == "https://api.example.com"


class TestExceptionStringRepresentation:
    """Verify informative string messages."""

    def test_message_in_str(self):
        err = NpsHikesError("something went wrong")
        assert str(err) == "something went wrong"

    def test_message_in_args(self):
        err = ConfigurationError("missing API key")
        assert err.args == ("missing API key",)

    def test_subclass_message(self):
        err = DatabaseWriteError(
            "Failed to write to osm_hikes",
            context={"table": "osm_hikes", "row_count": 42},
        )
        assert "osm_hikes" in str(err)
        assert err.context["row_count"] == 42


class TestExceptionCatching:
    """Verify exceptions can be caught at various levels of the hierarchy."""

    def test_catch_nps_hikes_error_catches_all_subclasses(self):
        """All project exceptions should be catchable via NpsHikesError."""
        exceptions = [
            ConfigurationError("test"),
            CollectorError("test"),
            ApiRequestError("test"),
            ApiResponseError("test"),
            SchemaValidationError("test"),
            DatabaseError("test"),
            DatabaseConnectionError("test"),
            DatabaseWriteError("test"),
            DataProcessingError("test"),
        ]
        for exc in exceptions:
            with pytest.raises(NpsHikesError):
                raise exc

    def test_catch_collector_error_catches_api_errors(self):
        with pytest.raises(CollectorError):
            raise ApiRequestError("timeout")
        with pytest.raises(CollectorError):
            raise ApiResponseError("bad json")
        with pytest.raises(CollectorError):
            raise SchemaValidationError("invalid schema")

    def test_catch_database_error_catches_db_subclasses(self):
        with pytest.raises(DatabaseError):
            raise DatabaseConnectionError("refused")
        with pytest.raises(DatabaseError):
            raise DatabaseWriteError("insert failed")

    def test_catch_exception_catches_all(self):
        """Backward compatibility: bare except Exception catches project exceptions."""
        with pytest.raises(ApiRequestError):
            raise ApiRequestError("test")
        # Also verify it's an Exception subclass
        assert issubclass(ApiRequestError, Exception)

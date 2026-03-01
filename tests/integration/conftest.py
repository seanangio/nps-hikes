"""
Integration test fixtures and configuration.

This module provides pytest fixtures for integration testing with a real PostGIS database.
The fixtures handle database lifecycle management, schema creation, and cleanup.

Key fixtures:
- test_db_engine: SQLAlchemy engine connected to test database
- test_db: Database with schema created and cleaned up after tests
- test_db_writer: DatabaseWriter instance for test operations

Usage:
    @pytest.mark.integration
    def test_my_integration(test_db_writer):
        # Use test_db_writer to interact with test database
        pass

Running integration tests:
    pytest tests/integration -v -m integration
"""

import os
import time

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from scripts.database.db_writer import DatabaseWriter
from utils.logging import setup_logging


def wait_for_db(
    engine: Engine, max_retries: int = 30, retry_delay: float = 1.0
) -> None:
    """
    Wait for database to be ready by attempting connections.

    Args:
        engine: SQLAlchemy engine to test
        max_retries: Maximum number of connection attempts
        retry_delay: Delay between retries in seconds

    Raises:
        RuntimeError: If database doesn't become ready within max_retries
    """
    for attempt in range(max_retries):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print(f"✅ Database ready after {attempt + 1} attempt(s)")
            return
        except Exception as e:
            if attempt < max_retries - 1:
                print(
                    f"⏳ Waiting for database (attempt {attempt + 1}/{max_retries})..."
                )
                time.sleep(retry_delay)
            else:
                raise RuntimeError(
                    f"Database not ready after {max_retries} attempts: {e}"
                ) from e


@pytest.fixture(scope="session")
def test_db_engine() -> Engine:
    """
    Create a SQLAlchemy engine for the test database.

    This fixture creates a database connection using test-specific credentials.
    The engine is reused across all tests in the session.

    Returns:
        Engine: SQLAlchemy engine connected to test database

    Environment Variables:
        POSTGRES_TEST_HOST: Test database host (default: localhost)
        POSTGRES_TEST_PORT: Test database port (default: 5434)
        POSTGRES_TEST_DB: Test database name (default: nps_hikes_test)
        POSTGRES_TEST_USER: Test database user (default: postgres)
        POSTGRES_TEST_PASSWORD: Test database password (default: test_password)
    """
    # Get test database configuration from environment
    host = os.getenv("POSTGRES_TEST_HOST", "localhost")
    port = os.getenv("POSTGRES_TEST_PORT", "5434")
    db = os.getenv("POSTGRES_TEST_DB", "nps_hikes_test")
    user = os.getenv("POSTGRES_TEST_USER", "postgres")
    password = os.getenv("POSTGRES_TEST_PASSWORD", "test_password")

    # Create connection string
    conn_str = f"postgresql://{user}:{password}@{host}:{port}/{db}"

    # Create engine
    engine = create_engine(conn_str)

    # Wait for database to be ready
    wait_for_db(engine)

    yield engine

    # Cleanup: close all connections
    engine.dispose()


@pytest.fixture(scope="function")
def test_db(test_db_engine: Engine) -> Engine:
    """
    Provide a clean database with schema for each test.

    This fixture:
    1. Creates all tables using the standardized SQL schemas
    2. Yields the engine to the test
    3. Drops all tables after the test completes

    This ensures each test starts with a clean database state and prevents
    test pollution.

    Args:
        test_db_engine: Session-scoped database engine

    Yields:
        Engine: Database engine with clean schema
    """
    logger = setup_logging(logger_name="test_db", log_level="INFO")
    writer = DatabaseWriter(test_db_engine, logger)

    # Setup: Create all tables
    logger.info("📦 Creating test database schema...")
    writer._create_all_tables()
    logger.info("✅ Test database schema created")

    yield test_db_engine

    # Teardown: Drop all tables
    logger.info("🧹 Cleaning up test database...")
    writer.drop_all_tables()
    logger.info("✅ Test database cleaned")


@pytest.fixture
def test_db_writer(test_db: Engine) -> DatabaseWriter:
    """
    Provide a DatabaseWriter instance for test operations.

    This fixture creates a DatabaseWriter connected to the test database,
    allowing tests to write and read data using the same interface as
    production code.

    Args:
        test_db: Clean test database with schema

    Returns:
        DatabaseWriter: Writer instance for test database operations
    """
    logger = setup_logging(logger_name="test_writer", log_level="DEBUG")
    return DatabaseWriter(test_db, logger)

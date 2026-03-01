# Integration Tests

This directory contains integration tests that verify the complete data flow through the NPS Hikes pipeline using a real PostGIS database.

## Overview

Integration tests validate:
- **Data Collection → Database**: Collectors write valid data to PostgreSQL/PostGIS
- **Database → API**: API endpoints query and return correct data
- **End-to-End Pipeline**: Complete orchestrator runs populate queryable data
- **Schema Compliance**: PostGIS geometries, constraints, and foreign keys work correctly

## Prerequisites

### Required
- Docker Desktop running
- Python 3.12+ with dev dependencies installed
- NPS API key set in environment

### Setup

```bash
# Install development dependencies (if not already done)
pip install -r requirements-dev.txt

# Ensure NPS_API_KEY is set
export NPS_API_KEY="your_api_key_here"

# Start test database
docker compose -f docker-compose.test.yml up -d

# Wait for database to be ready (watch for "database system is ready")
docker compose -f docker-compose.test.yml logs -f test-db
```

## Running Integration Tests

### Run all integration tests
```bash
pytest tests/integration -v -m integration
```

### Run specific test file
```bash
pytest tests/integration/test_nps_collector_db.py -v
```

### Run specific test
```bash
pytest tests/integration/test_nps_collector_db.py::TestNPSCollectorDatabaseIntegration::test_nps_collector_writes_park_metadata_to_database -v
```

### Run with verbose output
```bash
pytest tests/integration -v -s -m integration
```

## Test Database Configuration

The test database runs in a Docker container with these defaults:

- **Host**: localhost
- **Port**: 5434 (to avoid conflict with dev database on 5433)
- **Database**: nps_hikes_test
- **User**: postgres
- **Password**: test_password

### Custom Configuration

Override defaults using environment variables:

```bash
export POSTGRES_TEST_HOST=localhost
export POSTGRES_TEST_PORT=5434
export POSTGRES_TEST_DB=nps_hikes_test
export POSTGRES_TEST_USER=postgres
export POSTGRES_TEST_PASSWORD=test_password

pytest tests/integration -v -m integration
```

## Test Architecture

### Fixtures (conftest.py)

- **test_db_engine** (session): SQLAlchemy engine for test database
- **test_db** (function): Clean database with schema created/dropped per test
- **test_db_writer** (function): DatabaseWriter instance for test operations

### Current Tests

#### test_nps_collector_db.py (Phase 1: Foundation)
- ✅ Park metadata collection and database write
- ✅ Park boundary collection with PostGIS geometry validation
- ✅ Upsert behavior (updates instead of duplicate errors)
- ✅ Database constraint enforcement (PK, CHECK, FK)

#### test_trail_collectors_db.py (Phase 2: Trail Collectors)
- ✅ OSM trail collection via Overpass API → database
- ✅ OSM PostGIS geometry validation and spatial indexes
- ✅ TNM trail collection via USGS API → database
- ✅ TNM unique identifier (permanent_identifier) constraints

#### test_gmaps_importer_db.py (Phase 2: GMaps Locations)
- ✅ KML file parsing → database write
- ✅ Park code validation (FK constraint enforcement)
- ✅ Auto-incrementing ID generation
- ✅ Force refresh behavior (delete & replace)

## Performance Notes

Integration tests are slower than unit tests because they:
- Make real API calls (minimized with `limit=1`)
- Perform actual database I/O
- Create/drop schemas for each test

**Tip**: The test database uses tmpfs (RAM disk) for faster I/O and automatic cleanup.

## Cleanup

```bash
# Stop and remove test database
docker compose -f docker-compose.test.yml down -v

# The -v flag removes the volume, ensuring a clean state next time
```

## Troubleshooting

### "Connection refused" errors
- Ensure Docker is running: `docker ps`
- Check test database is healthy: `docker compose -f docker-compose.test.yml ps`
- View logs: `docker compose -f docker-compose.test.yml logs test-db`

### "NPS_API_KEY not set" skip messages
- Set your API key: `export NPS_API_KEY="your_key"`
- Or create a `.env` file with `NPS_API_KEY=your_key`

### Tests hang or timeout
- Check database health: `docker compose -f docker-compose.test.yml ps`
- Restart test database: `docker compose -f docker-compose.test.yml restart test-db`

### Schema errors
- Ensure SQL schema files are up to date in `sql/schema/`
- Check for migration conflicts if modifying schemas

## Adding New Integration Tests

1. Create test file in `tests/integration/`
2. Import fixtures from conftest.py
3. Mark tests with `@pytest.mark.integration` or `pytestmark = pytest.mark.integration`
4. Use `test_db_writer` fixture for database operations
5. Keep tests focused and fast (use `limit=1` for data collection)
6. Document what the test validates

Example:

```python
import pytest
from scripts.database.db_writer import DatabaseWriter

pytestmark = pytest.mark.integration

def test_my_integration(test_db_writer: DatabaseWriter):
    """Test description of what this validates."""
    # Arrange
    # Act
    # Assert
    pass
```

## CI/CD Integration

Integration tests are **configured and running** in GitHub Actions! The project uses a split workflow approach:

### Workflow Setup

**Unit Tests** ([.github/workflows/unit-tests.yml](../../.github/workflows/unit-tests.yml))
- Runs on: Every push to all branches
- Tests: `pytest tests/ -m "not integration"`
- Duration: ~Fast (no external APIs or database)

**Integration Tests** ([.github/workflows/integration-tests.yml](../../.github/workflows/integration-tests.yml))
- Runs on: Pull requests and pushes to `main` branch only
- Tests: `pytest tests/integration -m integration`
- Duration: ~2 minutes (includes external API calls)
- PostgreSQL: PostGIS service container on port 5434
- Environment:
  - `POSTGRES_TEST_HOST=localhost`
  - `POSTGRES_TEST_PORT=5434`
  - `POSTGRES_TEST_DB=nps_hikes_test`
  - `NPS_API_KEY` from GitHub secrets

### Why Split Workflows?

- **Fast feedback**: Unit tests run quickly on every commit
- **Resource efficiency**: Integration tests only run when needed
- **Reliability**: External API calls (OSM, TNM, NPS) can be slow/flaky - limiting runs reduces false failures
- **Clear separation**: Easy to see which type of test failed

### Viewing Test Results

Check the **Actions** tab in GitHub to see test runs. Both workflows must pass before merging PRs.

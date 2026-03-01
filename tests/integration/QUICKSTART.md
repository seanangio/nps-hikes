# Integration Tests - Quick Start

Get integration tests running in 5 minutes.

## Step 1: Start Test Database

```bash
# From project root
docker compose -f docker-compose.test.yml up -d
```

Wait ~10 seconds for database to initialize.

## Step 2: Verify Database is Ready

```bash
docker compose -f docker-compose.test.yml ps
```

Should show `test-db` as `healthy`.

## Step 3: Set NPS API Key

```bash
export NPS_API_KEY="your_nps_api_key_here"
```

## Step 4: Run Tests

```bash
# Run all integration tests
pytest tests/integration -v -m integration

# Or run just one test file
pytest tests/integration/test_nps_collector_db.py -v
```

## Step 5: View Results

You should see output like:

```
tests/integration/test_nps_collector_db.py::TestNPSCollectorDatabaseIntegration::test_nps_collector_writes_park_metadata_to_database PASSED
tests/integration/test_nps_collector_db.py::TestNPSCollectorDatabaseIntegration::test_nps_collector_writes_park_boundaries_to_database PASSED
tests/integration/test_nps_collector_db.py::TestNPSCollectorDatabaseIntegration::test_park_upsert_updates_existing_records PASSED
tests/integration/test_nps_collector_db.py::TestNPSCollectorDatabaseIntegration::test_database_constraints_enforced PASSED

====== 4 passed in 12.34s ======
```

## Step 6: Cleanup

```bash
docker compose -f docker-compose.test.yml down -v
```

The `-v` flag removes the test database volume for a clean slate next time.

## Troubleshooting

### Database not ready
```bash
# Check logs
docker compose -f docker-compose.test.yml logs test-db

# Restart
docker compose -f docker-compose.test.yml restart test-db
```

### Tests skipped with "NPS_API_KEY not set"
```bash
# Make sure your API key is exported
echo $NPS_API_KEY

# If empty, export it
export NPS_API_KEY="your_key_here"
```

### Connection refused
```bash
# Verify port 5434 is not in use
lsof -i :5434

# Verify Docker is running
docker ps
```

## What's Being Tested?

The example tests verify:
1. ✅ NPS collector fetches park data from real API
2. ✅ Data is written to PostgreSQL with correct schema
3. ✅ Park boundaries are stored as valid PostGIS geometries
4. ✅ Upsert operations work (no duplicate key errors)
5. ✅ Database constraints are enforced (PK, CHECK, FK)

This confirms the **Collector → Database** integration works correctly!

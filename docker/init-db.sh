#!/bin/bash
# Initialize the PostgreSQL database with required extensions and schema.
#
# This script runs automatically when the PostGIS container starts for
# the first time. It will NOT run again if the database already exists
# in the volume (standard PostgreSQL Docker behavior).

set -e

echo "Creating PostgreSQL extensions..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS postgis;
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
EOSQL

echo "Creating database tables..."

SCHEMA_DIR="/docker-entrypoint-initdb.d/schema"

# Run schema files in dependency order (parks first, then tables that reference it)
for schema_file in \
    "$SCHEMA_DIR/parks.sql" \
    "$SCHEMA_DIR/park_boundaries.sql" \
    "$SCHEMA_DIR/osm_hikes.sql" \
    "$SCHEMA_DIR/tnm_hikes.sql" \
    "$SCHEMA_DIR/gmaps_hiking_locations.sql" \
    "$SCHEMA_DIR/gmaps_hiking_locations_matched.sql" \
    "$SCHEMA_DIR/usgs_trail_elevations.sql"
do
    if [ -f "$schema_file" ]; then
        echo "Running $(basename "$schema_file")..."
        psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f "$schema_file"
    else
        echo "Warning: $schema_file not found, skipping."
    fi
done

echo "Database initialization complete."

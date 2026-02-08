-- USGS trail elevations table schema
-- Stores elevation profile data collected from USGS API for matched trails
-- Primary key: gmaps_location_id (1:1 relationship with gmaps_hiking_locations_matched)
-- Depends on: gmaps_hiking_locations_matched

CREATE TABLE IF NOT EXISTS usgs_trail_elevations (
    gmaps_location_id INTEGER PRIMARY KEY,
    trail_name VARCHAR(500),
    trail_slug VARCHAR(255),
    park_code VARCHAR(4) NOT NULL CHECK (park_code ~ '^[a-z]{4}$'),
    source VARCHAR(10), -- 'osm' or 'tnm'
    elevation_points JSONB,
    collection_status VARCHAR(20) DEFAULT 'COMPLETE',
    failed_points_count INTEGER DEFAULT 0,
    total_points_count INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_usgs_trail_elevations_gmaps_location_id_gmaps_hiking_locations_matched
        FOREIGN KEY (gmaps_location_id) REFERENCES gmaps_hiking_locations_matched(gmaps_location_id),
    CONSTRAINT fk_usgs_trail_elevations_park_code_parks
        FOREIGN KEY (park_code) REFERENCES parks(park_code)
);

-- Create performance indexes
CREATE INDEX IF NOT EXISTS idx_usgs_trail_elevations_gmaps_location_id
    ON usgs_trail_elevations (gmaps_location_id);
CREATE INDEX IF NOT EXISTS idx_usgs_trail_elevations_park_code
    ON usgs_trail_elevations (park_code);
CREATE INDEX IF NOT EXISTS idx_usgs_trail_elevations_trail_slug
    ON usgs_trail_elevations (trail_slug);
CREATE INDEX IF NOT EXISTS idx_usgs_trail_elevations_created_at
    ON usgs_trail_elevations (created_at);
CREATE INDEX IF NOT EXISTS idx_usgs_trail_elevations_collection_status
    ON usgs_trail_elevations (collection_status);
CREATE INDEX IF NOT EXISTS idx_usgs_trail_elevations_source
    ON usgs_trail_elevations (source);

-- Create composite indexes for common queries
CREATE INDEX IF NOT EXISTS idx_usgs_trail_elevations_park_code_source
    ON usgs_trail_elevations (park_code, source);
CREATE INDEX IF NOT EXISTS idx_usgs_trail_elevations_park_code_trail_slug
    ON usgs_trail_elevations (park_code, trail_slug);
CREATE INDEX IF NOT EXISTS idx_usgs_trail_elevations_status_source
    ON usgs_trail_elevations (collection_status, source);

-- Add table comments
COMMENT ON TABLE usgs_trail_elevations IS 'Elevation profile data for matched trails from USGS API';
COMMENT ON COLUMN usgs_trail_elevations.gmaps_location_id IS 'Primary key referencing matched trail in gmaps_hiking_locations_matched (1:1 relationship)';
COMMENT ON COLUMN usgs_trail_elevations.trail_slug IS 'URL-safe trail name for use in API endpoints (lowercase, underscores, no special characters)';
COMMENT ON COLUMN usgs_trail_elevations.elevation_points IS 'JSON array of elevation points with coordinates and elevation data';
COMMENT ON COLUMN usgs_trail_elevations.collection_status IS 'Status of elevation data collection';
COMMENT ON COLUMN usgs_trail_elevations.failed_points_count IS 'Number of elevation points that failed to collect';
COMMENT ON COLUMN usgs_trail_elevations.total_points_count IS 'Total number of elevation points attempted';

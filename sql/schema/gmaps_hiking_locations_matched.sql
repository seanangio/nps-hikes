-- Google Maps hiking locations matched table schema
-- Stores matched hiking locations with trail matching results
-- Primary key: gmaps_location_id (1:1 relationship with gmaps_hiking_locations)
-- Depends on: gmaps_hiking_locations

CREATE TABLE IF NOT EXISTS gmaps_hiking_locations_matched (
    gmaps_location_id INTEGER PRIMARY KEY,
    park_code VARCHAR(4) NOT NULL CHECK (park_code ~ '^[a-z]{4}$'),
    location_name VARCHAR(500) NOT NULL,
    latitude DECIMAL(15, 12),
    longitude DECIMAL(16, 12),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    matched_trail_name VARCHAR(500),
    source VARCHAR(10),
    name_similarity_score DECIMAL(5, 4),
    min_point_to_trail_distance_m DECIMAL(10, 2),
    confidence_score DECIMAL(5, 4),
    match_status VARCHAR(20),
    matched_trail_geometry geometry(GEOMETRY, 4326),

    CONSTRAINT fk_gmaps_hiking_locations_matched_gmaps_location_id_gmaps_hiking_locations
        FOREIGN KEY (gmaps_location_id) REFERENCES gmaps_hiking_locations(id),
    CONSTRAINT fk_gmaps_hiking_locations_matched_park_code_parks
        FOREIGN KEY (park_code) REFERENCES parks(park_code)
);

-- Create performance indexes
CREATE INDEX IF NOT EXISTS idx_gmaps_hiking_locations_matched_geometry ON gmaps_hiking_locations_matched USING GIST (matched_trail_geometry);
CREATE INDEX IF NOT EXISTS idx_gmaps_hiking_locations_matched_park_code ON gmaps_hiking_locations_matched (park_code);
CREATE INDEX IF NOT EXISTS idx_gmaps_hiking_locations_matched_gmaps_location_id ON gmaps_hiking_locations_matched (gmaps_location_id);
CREATE INDEX IF NOT EXISTS idx_gmaps_hiking_locations_matched_confidence_score ON gmaps_hiking_locations_matched (confidence_score);
CREATE INDEX IF NOT EXISTS idx_gmaps_hiking_locations_matched_match_status ON gmaps_hiking_locations_matched (match_status);

-- Add table comments
COMMENT ON TABLE gmaps_hiking_locations_matched IS 'Matched hiking locations with trail matching results';
COMMENT ON COLUMN gmaps_hiking_locations_matched.gmaps_location_id IS 'Primary key referencing original location in gmaps_hiking_locations (1:1 relationship)';
COMMENT ON COLUMN gmaps_hiking_locations_matched.confidence_score IS 'Confidence score for trail match (0.0 to 1.0)';
COMMENT ON COLUMN gmaps_hiking_locations_matched.min_point_to_trail_distance_m IS 'Distance in meters between location and matched trail';
COMMENT ON COLUMN gmaps_hiking_locations_matched.source IS 'Source of matched trail data (osm or tnm)';

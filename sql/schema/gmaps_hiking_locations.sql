-- Google Maps hiking locations table schema
-- Stores hiking location data with coordinates from Google Maps
-- Primary key: serial id (auto-incrementing)

CREATE TABLE IF NOT EXISTS gmaps_hiking_locations (
    id SERIAL PRIMARY KEY,
    park_code VARCHAR(4) NOT NULL CHECK (park_code ~ '^[a-z]{4}$'),
    location_name VARCHAR(500) NOT NULL,
    latitude DECIMAL(10,8),
    longitude DECIMAL(11,8),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_gmaps_hiking_locations_park_code_parks
        FOREIGN KEY (park_code) REFERENCES parks(park_code),

    -- Coordinate validation constraints
    CONSTRAINT chk_gmaps_latitude CHECK (latitude BETWEEN -90 AND 90),
    CONSTRAINT chk_gmaps_longitude CHECK (longitude BETWEEN -180 AND 180)
);

-- Create performance indexes
CREATE INDEX IF NOT EXISTS idx_gmaps_hiking_locations_park_code
    ON gmaps_hiking_locations (park_code);
CREATE INDEX IF NOT EXISTS idx_gmaps_hiking_locations_created_at
    ON gmaps_hiking_locations (created_at);
CREATE INDEX IF NOT EXISTS idx_gmaps_hiking_locations_location_name
    ON gmaps_hiking_locations (location_name);

-- Create composite indexes for common queries
CREATE INDEX IF NOT EXISTS idx_gmaps_hiking_locations_park_code_location
    ON gmaps_hiking_locations (park_code, location_name);

-- Add table comments
COMMENT ON TABLE gmaps_hiking_locations IS 'Hiking location data from Google Maps';
COMMENT ON COLUMN gmaps_hiking_locations.park_code IS '4-character lowercase park identifier, references parks table';
COMMENT ON COLUMN gmaps_hiking_locations.location_name IS 'Name of the hiking location from Google Maps';
COMMENT ON COLUMN gmaps_hiking_locations.latitude IS 'Latitude coordinate with 8 decimal places precision (~1 meter accuracy)';
COMMENT ON COLUMN gmaps_hiking_locations.longitude IS 'Longitude coordinate with 8 decimal places precision (~1 meter accuracy)';

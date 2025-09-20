-- Google Maps hiking locations table schema
-- Stores hiking location data with coordinates from Google Maps
-- Primary key: serial id (auto-incrementing)

CREATE TABLE IF NOT EXISTS gmaps_hiking_locations (
    id SERIAL PRIMARY KEY,
    park_code VARCHAR(4) NOT NULL CHECK (park_code ~ '^[a-z]{4}$'),
    location_name VARCHAR(500) NOT NULL,
    latitude DECIMAL(15, 12),
    longitude DECIMAL(16, 12),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CONSTRAINT fk_gmaps_hiking_locations_park_code_parks 
        FOREIGN KEY (park_code) REFERENCES parks(park_code)
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
COMMENT ON COLUMN gmaps_hiking_locations.latitude IS 'Latitude coordinate (15,12 precision for accuracy)';
COMMENT ON COLUMN gmaps_hiking_locations.longitude IS 'Longitude coordinate (16,12 precision for accuracy)';

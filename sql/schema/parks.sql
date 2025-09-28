-- Parks table schema
-- Stores National Park Service park metadata including names, coordinates, descriptions
-- Primary key: park_code (4-character lowercase identifier)

CREATE TABLE IF NOT EXISTS parks (
    park_code VARCHAR(4) NOT NULL CHECK (park_code ~ '^[a-z]{4}$'),
    park_name VARCHAR(255),
    visit_month VARCHAR(10),
    visit_year INTEGER,
    full_name TEXT,
    states VARCHAR(100),
    url TEXT,
    latitude DECIMAL(10,8),
    longitude DECIMAL(11,8),
    description TEXT,
    error_message TEXT,
    collection_status VARCHAR(20),
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    PRIMARY KEY (park_code),
    
    -- Coordinate validation constraints
    CONSTRAINT chk_parks_latitude CHECK (latitude BETWEEN -90 AND 90),
    CONSTRAINT chk_parks_longitude CHECK (longitude BETWEEN -180 AND 180)
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_parks_collected_at ON parks (collected_at);
CREATE INDEX IF NOT EXISTS idx_parks_collection_status ON parks (collection_status);
CREATE INDEX IF NOT EXISTS idx_parks_states ON parks (states);

-- Add table comments
COMMENT ON TABLE parks IS 'National Park Service park metadata and basic information';
COMMENT ON COLUMN parks.park_code IS '4-character lowercase park identifier (e.g., yell, grca)';
COMMENT ON COLUMN parks.visit_month IS 'Month of park visit from raw_data/parks.csv';
COMMENT ON COLUMN parks.visit_year IS 'Year of park visit from raw_data/parks.csv';
COMMENT ON COLUMN parks.full_name IS 'Official full name of the park';
COMMENT ON COLUMN parks.collection_status IS 'Status of data collection (success, error, etc.)';
COMMENT ON COLUMN parks.collected_at IS 'Timestamp when park data was collected';
COMMENT ON COLUMN parks.latitude IS 'Latitude coordinate with 8 decimal places precision (~1 meter accuracy)';
COMMENT ON COLUMN parks.longitude IS 'Longitude coordinate with 8 decimal places precision (~1 meter accuracy)';

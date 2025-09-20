-- OSM hikes table schema
-- Stores hiking trail data from OpenStreetMap
-- Primary key: composite (park_code, osm_id) to handle multiple trail segments

CREATE TABLE IF NOT EXISTS osm_hikes (
    osm_id BIGINT NOT NULL,
    park_code VARCHAR(4) NOT NULL CHECK (park_code ~ '^[a-z]{4}$'),
    highway VARCHAR(50) NOT NULL,
    name VARCHAR(500),
    source VARCHAR(100),
    length_mi DOUBLE PRECISION NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    geometry_type VARCHAR(50) NOT NULL,
    geometry geometry(LINESTRING, 4326) NOT NULL,
    
    PRIMARY KEY (park_code, osm_id),
    
    CONSTRAINT fk_osm_hikes_park_code_parks 
        FOREIGN KEY (park_code) REFERENCES parks(park_code)
);

-- Create spatial index for geometry queries
CREATE INDEX IF NOT EXISTS idx_osm_hikes_geometry 
    ON osm_hikes USING GIST (geometry);

-- Create performance indexes
CREATE INDEX IF NOT EXISTS idx_osm_hikes_park_code 
    ON osm_hikes (park_code);
CREATE INDEX IF NOT EXISTS idx_osm_hikes_collected_at 
    ON osm_hikes (collected_at);
CREATE INDEX IF NOT EXISTS idx_osm_hikes_highway 
    ON osm_hikes (highway);
CREATE INDEX IF NOT EXISTS idx_osm_hikes_length_mi 
    ON osm_hikes (length_mi);

-- Create composite indexes for common queries
CREATE INDEX IF NOT EXISTS idx_osm_hikes_park_code_highway 
    ON osm_hikes (park_code, highway);
CREATE INDEX IF NOT EXISTS idx_osm_hikes_park_code_length 
    ON osm_hikes (park_code, length_mi);

-- Add table comments
COMMENT ON TABLE osm_hikes IS 'Hiking trail data from OpenStreetMap';
COMMENT ON COLUMN osm_hikes.osm_id IS 'OpenStreetMap feature ID (may be modified for trail segments)';
COMMENT ON COLUMN osm_hikes.park_code IS '4-character lowercase park identifier, references parks table';
COMMENT ON COLUMN osm_hikes.highway IS 'OSM highway tag value (path, footway, etc.)';
COMMENT ON COLUMN osm_hikes.length_mi IS 'Trail length in miles calculated using projected coordinate system';
COMMENT ON COLUMN osm_hikes.geometry IS 'LineString geometry in WGS84 (EPSG:4326)';

-- Park boundaries table schema
-- Stores spatial boundary polygons for National Parks
-- Primary key: park_code (one-to-one relationship with parks table)

CREATE TABLE IF NOT EXISTS park_boundaries (
    park_code VARCHAR(4) NOT NULL CHECK (park_code ~ '^[a-z]{4}$'),
    boundary_source VARCHAR(50),
    collection_status VARCHAR(20),
    error_message TEXT,
    bbox VARCHAR(100), -- Bounding box as "xmin,ymin,xmax,ymax" string
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    geometry_type VARCHAR(50),
    geometry geometry(MULTIPOLYGON, 4326),
    
    PRIMARY KEY (park_code),
    
    CONSTRAINT fk_park_boundaries_park_code_parks 
        FOREIGN KEY (park_code) REFERENCES parks(park_code)
);

-- Create spatial index for geometry queries
CREATE INDEX IF NOT EXISTS idx_park_boundaries_geometry 
    ON park_boundaries USING GIST (geometry);

-- Create performance indexes
CREATE INDEX IF NOT EXISTS idx_park_boundaries_collected_at 
    ON park_boundaries (collected_at);
CREATE INDEX IF NOT EXISTS idx_park_boundaries_collection_status 
    ON park_boundaries (collection_status);
CREATE INDEX IF NOT EXISTS idx_park_boundaries_boundary_source 
    ON park_boundaries (boundary_source);

-- Add table comments
COMMENT ON TABLE park_boundaries IS 'Spatial boundary polygons for National Parks';
COMMENT ON COLUMN park_boundaries.park_code IS '4-character lowercase park identifier, references parks table';
COMMENT ON COLUMN park_boundaries.geometry IS 'MultiPolygon geometry in WGS84 (EPSG:4326)';
COMMENT ON COLUMN park_boundaries.bbox IS 'Bounding box coordinates as "xmin,ymin,xmax,ymax" string';
COMMENT ON COLUMN park_boundaries.boundary_source IS 'Source of boundary data (NPS, USGS, etc.)';

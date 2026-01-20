-- TNM hikes table schema
-- Stores hiking trail data from The National Map (USGS)
-- Primary key: permanent_identifier (globally unique from TNM API)

CREATE TABLE IF NOT EXISTS tnm_hikes (
    permanent_identifier VARCHAR(100) PRIMARY KEY,
    park_code VARCHAR(4) NOT NULL CHECK (park_code ~ '^[a-z]{4}$'),
    object_id INTEGER,
    name VARCHAR(500),
    name_alternate VARCHAR(500),
    trail_number VARCHAR(50),
    trail_number_alternate VARCHAR(50),
    source_feature_id VARCHAR(100),
    source_dataset_id VARCHAR(100),
    source_originator VARCHAR(100),
    load_date BIGINT,
    trail_type VARCHAR(100),
    hiker_pedestrian VARCHAR(1),
    bicycle VARCHAR(1),
    pack_saddle VARCHAR(1),
    atv VARCHAR(1),
    motorcycle VARCHAR(1),
    ohv_over_50_inches VARCHAR(1),
    snowshoe VARCHAR(1),
    cross_country_ski VARCHAR(1),
    dogsled VARCHAR(1),
    snowmobile VARCHAR(1),
    non_motorized_watercraft VARCHAR(1),
    motorized_watercraft VARCHAR(1),
    primary_trail_maintainer VARCHAR(100),
    national_trail_designation VARCHAR(500),
    length_miles DECIMAL(8,3),
    network_length DOUBLE PRECISION,
    shape_length DOUBLE PRECISION,
    source_data_description VARCHAR(500),
    global_id VARCHAR(100),
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    geometry_type VARCHAR(50) NOT NULL,
    geometry geometry(GEOMETRY, 4326) NOT NULL,

    CONSTRAINT fk_tnm_hikes_park_code_parks
        FOREIGN KEY (park_code) REFERENCES parks(park_code),

    -- Length validation constraint
    CONSTRAINT chk_tnm_length CHECK (length_miles > 0 AND length_miles < 1000)
);

-- Create spatial index for geometry queries
CREATE INDEX IF NOT EXISTS idx_tnm_hikes_geometry
    ON tnm_hikes USING GIST (geometry);

-- Create performance indexes
CREATE INDEX IF NOT EXISTS idx_tnm_hikes_park_code
    ON tnm_hikes (park_code);
CREATE INDEX IF NOT EXISTS idx_tnm_hikes_collected_at
    ON tnm_hikes (collected_at);
CREATE INDEX IF NOT EXISTS idx_tnm_hikes_trail_type
    ON tnm_hikes (trail_type);
CREATE INDEX IF NOT EXISTS idx_tnm_hikes_hiker_pedestrian
    ON tnm_hikes (hiker_pedestrian);
CREATE INDEX IF NOT EXISTS idx_tnm_hikes_length_miles
    ON tnm_hikes (length_miles);
CREATE INDEX IF NOT EXISTS idx_tnm_hikes_primary_trail_maintainer
    ON tnm_hikes (primary_trail_maintainer);

-- Create composite indexes for common queries
CREATE INDEX IF NOT EXISTS idx_tnm_hikes_park_code_trail_type
    ON tnm_hikes (park_code, trail_type);
CREATE INDEX IF NOT EXISTS idx_tnm_hikes_park_code_hiker_pedestrian
    ON tnm_hikes (park_code, hiker_pedestrian);
CREATE INDEX IF NOT EXISTS idx_tnm_hikes_park_code_length
    ON tnm_hikes (park_code, length_miles);

-- Add table comments
COMMENT ON TABLE tnm_hikes IS 'Hiking trail data from The National Map (USGS)';
COMMENT ON COLUMN tnm_hikes.permanent_identifier IS 'Globally unique identifier from TNM API';
COMMENT ON COLUMN tnm_hikes.park_code IS '4-character lowercase park identifier, references parks table';
COMMENT ON COLUMN tnm_hikes.trail_type IS 'Type of trail (Terra Trail, etc.)';
COMMENT ON COLUMN tnm_hikes.hiker_pedestrian IS 'Allows hiking/pedestrian use (Y/N)';
COMMENT ON COLUMN tnm_hikes.bicycle IS 'Allows bicycle use (Y/N)';
COMMENT ON COLUMN tnm_hikes.length_miles IS 'Trail length in miles with 3 decimal places precision (0.001 mile = ~5 feet)';
COMMENT ON COLUMN tnm_hikes.primary_trail_maintainer IS 'Organization responsible for trail maintenance';
COMMENT ON COLUMN tnm_hikes.geometry IS 'Trail geometry in WGS84 (EPSG:4326)';

-- NPS Content tables schema
-- Stores rich text content from NPS API /thingstodo and /places endpoints,
-- plus vector embeddings for semantic search via pgvector.

-- Things to do at each park
CREATE TABLE IF NOT EXISTS nps_thingstodo (
    id VARCHAR(100) NOT NULL,
    park_code VARCHAR(4) NOT NULL,
    title TEXT NOT NULL,
    short_description TEXT,
    long_description TEXT,
    activities JSONB DEFAULT '[]'::jsonb,
    topics JSONB DEFAULT '[]'::jsonb,
    tags JSONB DEFAULT '[]'::jsonb,
    season JSONB DEFAULT '[]'::jsonb,
    duration VARCHAR(100),
    pets_description TEXT,
    fees_description TEXT,
    accessibility TEXT,
    location_description TEXT,
    url TEXT,
    latitude DECIMAL(10,8),
    longitude DECIMAL(11,8),
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (id),
    FOREIGN KEY (park_code) REFERENCES parks(park_code),

    CONSTRAINT chk_thingstodo_latitude CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90),
    CONSTRAINT chk_thingstodo_longitude CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180)
);

CREATE INDEX IF NOT EXISTS idx_thingstodo_park_code ON nps_thingstodo (park_code);

COMMENT ON TABLE nps_thingstodo IS 'Things to do content from the NPS API /thingstodo endpoint';
COMMENT ON COLUMN nps_thingstodo.id IS 'Unique identifier from the NPS API';
COMMENT ON COLUMN nps_thingstodo.park_code IS '4-character lowercase park identifier';
COMMENT ON COLUMN nps_thingstodo.activities IS 'JSONB array of activity objects';
COMMENT ON COLUMN nps_thingstodo.season IS 'JSONB array of seasons when the activity is available';

-- Places within each park
CREATE TABLE IF NOT EXISTS nps_places (
    id VARCHAR(100) NOT NULL,
    park_code VARCHAR(4) NOT NULL,
    title TEXT NOT NULL,
    short_description TEXT,
    body_text TEXT,
    audio_description TEXT,
    tags JSONB DEFAULT '[]'::jsonb,
    url TEXT,
    latitude DECIMAL(10,8),
    longitude DECIMAL(11,8),
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (id),
    FOREIGN KEY (park_code) REFERENCES parks(park_code),

    CONSTRAINT chk_places_latitude CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90),
    CONSTRAINT chk_places_longitude CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180)
);

CREATE INDEX IF NOT EXISTS idx_places_park_code ON nps_places (park_code);

COMMENT ON TABLE nps_places IS 'Places content from the NPS API /places endpoint';
COMMENT ON COLUMN nps_places.id IS 'Unique identifier from the NPS API';
COMMENT ON COLUMN nps_places.park_code IS '4-character lowercase park identifier';
COMMENT ON COLUMN nps_places.body_text IS 'Full body text with HTML stripped';

-- Content embeddings for vector search
CREATE TABLE IF NOT EXISTS content_embeddings (
    id SERIAL NOT NULL,
    park_code VARCHAR(4) NOT NULL,
    source_type VARCHAR(30) NOT NULL,
    source_id VARCHAR(100),
    title TEXT,
    chunk_text TEXT NOT NULL,
    embedding vector(768) NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (id),
    FOREIGN KEY (park_code) REFERENCES parks(park_code),

    CONSTRAINT chk_embeddings_source_type CHECK (source_type IN ('thingstodo', 'places', 'park_description'))
);

CREATE INDEX IF NOT EXISTS idx_embeddings_park_code ON content_embeddings (park_code);
CREATE INDEX IF NOT EXISTS idx_embeddings_source_type ON content_embeddings (source_type);

-- HNSW index for efficient approximate nearest neighbor search
-- cosine distance operator: <=>
CREATE INDEX IF NOT EXISTS idx_embeddings_vector ON content_embeddings
    USING hnsw (embedding vector_cosine_ops);

COMMENT ON TABLE content_embeddings IS 'Vector embeddings for semantic search over NPS content';
COMMENT ON COLUMN content_embeddings.source_type IS 'Content source: thingstodo, places, or park_description';
COMMENT ON COLUMN content_embeddings.source_id IS 'ID of the source record in its origin table';
COMMENT ON COLUMN content_embeddings.chunk_text IS 'The text that was embedded';
COMMENT ON COLUMN content_embeddings.embedding IS '768-dimensional vector from nomic-embed-text model';
COMMENT ON COLUMN content_embeddings.metadata IS 'Additional metadata (tags, season, duration, etc.)';

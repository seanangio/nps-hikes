-- Content-Trail Mapping table
-- Pre-computed mapping between NPS content embeddings and trail records.
-- Used to bridge semantic search results back to structured trail data.

CREATE TABLE IF NOT EXISTS content_trail_mapping (
    id SERIAL PRIMARY KEY,
    content_embedding_id INTEGER NOT NULL REFERENCES content_embeddings(id) ON DELETE CASCADE,
    park_code VARCHAR(4) NOT NULL,
    trail_name VARCHAR(500) NOT NULL,
    trail_source VARCHAR(3) NOT NULL CHECK (trail_source IN ('TNM', 'OSM')),
    trail_id VARCHAR(100) NOT NULL,
    content_title TEXT NOT NULL,
    name_similarity_score FLOAT NOT NULL,
    match_confidence FLOAT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ctm_embedding_id ON content_trail_mapping (content_embedding_id);
CREATE INDEX IF NOT EXISTS idx_ctm_park_trail ON content_trail_mapping (park_code, trail_name);
CREATE INDEX IF NOT EXISTS idx_ctm_trail_id ON content_trail_mapping (trail_id);

COMMENT ON TABLE content_trail_mapping IS 'Pre-computed mapping between content embeddings and trail records for semantic trail search';
COMMENT ON COLUMN content_trail_mapping.content_embedding_id IS 'FK to content_embeddings.id (CASCADE on delete)';
COMMENT ON COLUMN content_trail_mapping.trail_source IS 'Trail data source: TNM or OSM';
COMMENT ON COLUMN content_trail_mapping.trail_id IS 'permanent_identifier (TNM) or osm_id::text (OSM)';
COMMENT ON COLUMN content_trail_mapping.content_title IS 'Original content title for debugging';
COMMENT ON COLUMN content_trail_mapping.name_similarity_score IS 'Raw name similarity from SequenceMatcher';
COMMENT ON COLUMN content_trail_mapping.match_confidence IS 'Final match confidence score after boosts';

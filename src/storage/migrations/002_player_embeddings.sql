-- Player identity embeddings for semantic matching
-- Uses OpenAI text-embedding-3-small (1536 dimensions)

CREATE TABLE IF NOT EXISTS scouting.player_embeddings (
    id SERIAL PRIMARY KEY,
    roster_id TEXT NOT NULL,
    identity_text TEXT NOT NULL,
    embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- HNSW index for fast cosine similarity search
CREATE INDEX IF NOT EXISTS idx_player_embeddings_hnsw
    ON scouting.player_embeddings
    USING hnsw (embedding vector_cosine_ops);

-- Index for roster_id lookups
CREATE INDEX IF NOT EXISTS idx_player_embeddings_roster
    ON scouting.player_embeddings (roster_id);

-- Prevent duplicate embeddings per roster player
CREATE UNIQUE INDEX IF NOT EXISTS idx_player_embeddings_unique_roster
    ON scouting.player_embeddings (roster_id);

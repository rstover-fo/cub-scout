-- High-performance HNSW index for vector similarity matching
-- This speeds up the Tier 2 matching in the cub-scout pipeline.
-- Requires pgvector extension to be enabled.

CREATE INDEX IF NOT EXISTS idx_player_embeddings_hnsw 
ON scouting.player_embeddings 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Comment: m=16 and ef_construction=64 are good defaults for a ~30k-100k row table
-- balancing index speed vs accuracy.

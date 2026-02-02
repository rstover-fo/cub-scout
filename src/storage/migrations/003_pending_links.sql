-- Pending player links for manual review
-- Captures uncertain matches from fuzzy/vector matching

CREATE TABLE IF NOT EXISTS scouting.pending_links (
    id SERIAL PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_team TEXT,
    source_context JSONB DEFAULT '{}',
    candidate_roster_id TEXT,
    match_score FLOAT,
    match_method TEXT CHECK (match_method IN ('vector', 'fuzzy', 'deterministic')),
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pending_links_status
    ON scouting.pending_links (status)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_pending_links_created
    ON scouting.pending_links (created_at DESC);

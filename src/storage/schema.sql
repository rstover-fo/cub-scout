-- CFB Scout Schema
-- Deploy to Supabase using SQL Editor or migration tool

CREATE SCHEMA IF NOT EXISTS scouting;

-- Raw crawled content
CREATE TABLE IF NOT EXISTS scouting.reports (
    id SERIAL PRIMARY KEY,
    source_url TEXT NOT NULL,
    source_name TEXT NOT NULL,
    published_at TIMESTAMPTZ,
    crawled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    content_type TEXT NOT NULL CHECK (content_type IN ('article', 'social', 'forum')),
    player_ids BIGINT[] DEFAULT '{}',
    team_ids TEXT[] DEFAULT '{}',
    raw_text TEXT NOT NULL,
    summary TEXT,
    sentiment_score NUMERIC(3,2) CHECK (sentiment_score BETWEEN -1 AND 1),
    processed_at TIMESTAMPTZ,
    UNIQUE (source_url)
);

CREATE INDEX idx_reports_source ON scouting.reports (source_name);
CREATE INDEX idx_reports_crawled ON scouting.reports (crawled_at DESC);
CREATE INDEX idx_reports_unprocessed ON scouting.reports (id) WHERE processed_at IS NULL;
CREATE INDEX idx_reports_players ON scouting.reports USING GIN (player_ids);
CREATE INDEX idx_reports_teams ON scouting.reports USING GIN (team_ids);

-- Player scouting profiles
CREATE TABLE IF NOT EXISTS scouting.players (
    id SERIAL PRIMARY KEY,
    roster_player_id BIGINT,  -- Links to core.roster.id
    recruit_id BIGINT,        -- Links to recruiting.recruits.id
    name TEXT NOT NULL,
    position TEXT,
    team TEXT,
    class_year INT,
    current_status TEXT CHECK (current_status IN ('recruit', 'active', 'transfer', 'draft_eligible', 'drafted')),
    composite_grade INT CHECK (composite_grade BETWEEN 0 AND 100),
    traits JSONB DEFAULT '{}',
    draft_projection TEXT,
    comps TEXT[] DEFAULT '{}',
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (name, team, class_year)
);

CREATE INDEX idx_players_team ON scouting.players (team);
CREATE INDEX idx_players_status ON scouting.players (current_status);
CREATE INDEX idx_players_grade ON scouting.players (composite_grade DESC NULLS LAST);

-- Player timeline for longitudinal tracking
CREATE TABLE IF NOT EXISTS scouting.player_timeline (
    id SERIAL PRIMARY KEY,
    player_id INT NOT NULL REFERENCES scouting.players(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL,
    status TEXT,
    sentiment_score NUMERIC(3,2),
    grade_at_time INT,
    traits_at_time JSONB,
    key_narratives TEXT[] DEFAULT '{}',
    sources_count INT DEFAULT 0,
    UNIQUE (player_id, snapshot_date)
);

CREATE INDEX idx_timeline_player ON scouting.player_timeline (player_id);
CREATE INDEX idx_timeline_date ON scouting.player_timeline (snapshot_date DESC);

-- Team roster analysis
CREATE TABLE IF NOT EXISTS scouting.team_rosters (
    id SERIAL PRIMARY KEY,
    team TEXT NOT NULL,
    season INT NOT NULL,
    position_groups JSONB DEFAULT '{}',
    overall_sentiment NUMERIC(3,2),
    trajectory TEXT CHECK (trajectory IN ('improving', 'stable', 'declining')),
    key_storylines TEXT[] DEFAULT '{}',
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (team, season)
);

CREATE INDEX idx_team_rosters_team ON scouting.team_rosters (team);
CREATE INDEX idx_team_rosters_season ON scouting.team_rosters (season DESC);

-- Crawl job tracking
CREATE TABLE IF NOT EXISTS scouting.crawl_jobs (
    id SERIAL PRIMARY KEY,
    source_name TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed')),
    records_crawled INT DEFAULT 0,
    records_new INT DEFAULT 0,
    error_message TEXT
);

CREATE INDEX idx_crawl_jobs_source ON scouting.crawl_jobs (source_name, started_at DESC);

-- PFF grade snapshots
CREATE TABLE IF NOT EXISTS scouting.pff_grades (
    id SERIAL PRIMARY KEY,
    player_id INT REFERENCES scouting.players(id) ON DELETE CASCADE,
    pff_player_id TEXT NOT NULL,
    season INT NOT NULL,
    week INT,  -- NULL for season-long grades
    overall_grade NUMERIC(4,1) NOT NULL,
    position_grades JSONB DEFAULT '{}',
    snaps INT DEFAULT 0,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (player_id, season, week)
);

CREATE INDEX idx_pff_grades_player ON scouting.pff_grades (player_id);
CREATE INDEX idx_pff_grades_season ON scouting.pff_grades (season, week);

-- User watch lists
CREATE TABLE IF NOT EXISTS scouting.watch_lists (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    user_id TEXT NOT NULL,  -- External user identifier
    description TEXT,
    player_ids INT[] DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, name)
);

CREATE INDEX idx_watch_lists_user ON scouting.watch_lists (user_id);

-- Alert rules for watched players
CREATE TABLE IF NOT EXISTS scouting.alerts (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    alert_type TEXT NOT NULL CHECK (alert_type IN ('grade_change', 'new_report', 'status_change', 'trend_change', 'portal_entry')),
    player_id INT REFERENCES scouting.players(id) ON DELETE CASCADE,
    team TEXT,  -- NULL for player-specific, set for team-wide alerts
    threshold JSONB DEFAULT '{}',  -- type-specific config (e.g., {"min_change": 5})
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_checked_at TIMESTAMPTZ,
    UNIQUE (user_id, name)
);

CREATE INDEX idx_alerts_user ON scouting.alerts (user_id);
CREATE INDEX idx_alerts_player ON scouting.alerts (player_id);
CREATE INDEX idx_alerts_active ON scouting.alerts (is_active) WHERE is_active = TRUE;

-- Fired alert history
CREATE TABLE IF NOT EXISTS scouting.alert_history (
    id SERIAL PRIMARY KEY,
    alert_id INT NOT NULL REFERENCES scouting.alerts(id) ON DELETE CASCADE,
    fired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    trigger_data JSONB NOT NULL,  -- What triggered it (old_grade, new_grade, report_id, etc.)
    message TEXT NOT NULL,
    is_read BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_alert_history_alert ON scouting.alert_history (alert_id);
CREATE INDEX idx_alert_history_unread ON scouting.alert_history (is_read) WHERE is_read = FALSE;

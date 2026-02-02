-- Indexes for common player_mart query patterns
-- Applied after mat view creation

-- Team roster queries
CREATE INDEX IF NOT EXISTS idx_player_mart_team
  ON scouting.player_mart (team);

-- Position filtering
CREATE INDEX IF NOT EXISTS idx_player_mart_position
  ON scouting.player_mart (position);

-- Portal tracker (only non-null portal_status)
CREATE INDEX IF NOT EXISTS idx_player_mart_portal
  ON scouting.player_mart (portal_status)
  WHERE portal_status IS NOT NULL;

-- Scouting grade rankings
CREATE INDEX IF NOT EXISTS idx_player_mart_grade
  ON scouting.player_mart (composite_grade DESC NULLS LAST);

-- Recruiting star ratings
CREATE INDEX IF NOT EXISTS idx_player_mart_stars
  ON scouting.player_mart (stars DESC NULLS LAST);

-- Combined team + position (common filter)
CREATE INDEX IF NOT EXISTS idx_player_mart_team_position
  ON scouting.player_mart (team, position);

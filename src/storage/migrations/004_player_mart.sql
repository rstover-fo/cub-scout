-- Unified Player Mart: Single queryable entity for all player data
-- Joins roster, recruiting, scouting, and transfer data
-- Refresh nightly via pg_cron or manual REFRESH MATERIALIZED VIEW
-- Uses DISTINCT ON to handle players on multiple rosters (transfers)

CREATE MATERIALIZED VIEW IF NOT EXISTS scouting.player_mart AS
SELECT DISTINCT ON (r.id)
  -- Identity (canonical from roster)
  r.id AS player_id,
  r.first_name || ' ' || r.last_name AS name,
  r.team,
  r.position,
  r.year AS roster_year,

  -- Demographics
  r.height,
  r.weight,
  r.jersey,
  r.home_city,
  r.home_state,

  -- Recruiting data (via athlete_id link)
  rec.stars,
  rec.rating AS recruit_rating,
  rec.ranking AS national_ranking,
  rec.year AS recruit_class,
  rec.school AS high_school,

  -- Scouting intelligence
  sp.id AS scouting_id,
  sp.composite_grade,
  sp.traits,
  sp.draft_projection,
  sp.comps,
  sp.current_status AS scouting_status,

  -- Portal status (latest event for this player)
  latest_te.event_type AS portal_status,
  latest_te.to_team AS portal_destination,
  latest_te.event_date AS portal_date

FROM core.roster r

-- Join recruiting data via athlete_id
LEFT JOIN recruiting.recruits rec
  ON rec.athlete_id = r.id

-- Join scouting data via roster_player_id
LEFT JOIN scouting.players sp
  ON sp.roster_player_id = r.id::bigint

-- Join latest transfer event via scouting.players.id
LEFT JOIN LATERAL (
  SELECT te.event_type, te.to_team, te.event_date
  FROM scouting.transfer_events te
  WHERE te.player_id = sp.id
  ORDER BY te.event_date DESC
  LIMIT 1
) latest_te ON true

-- Only include current roster year
WHERE r.year = (SELECT MAX(year) FROM core.roster)

-- Pick most recent record per player (handles transfers)
ORDER BY r.id, r._dlt_load_id DESC;

-- Add unique index for CONCURRENTLY refresh
CREATE UNIQUE INDEX IF NOT EXISTS idx_player_mart_player_id
  ON scouting.player_mart (player_id);

COMMENT ON MATERIALIZED VIEW scouting.player_mart IS
  'Unified player entity joining roster, recruiting, scouting, and portal data. Refresh nightly.';

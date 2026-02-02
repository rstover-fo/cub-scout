-- Function to refresh player_mart materialized view
-- Can be called manually or scheduled via pg_cron

CREATE OR REPLACE FUNCTION scouting.refresh_player_mart()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  REFRESH MATERIALIZED VIEW CONCURRENTLY scouting.player_mart;
END;
$$;

COMMENT ON FUNCTION scouting.refresh_player_mart() IS
  'Refreshes player_mart materialized view. Uses CONCURRENTLY to avoid locking reads.';

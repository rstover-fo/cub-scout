# Phase 6B: Unified Player Mart Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create the unified player mart materialized view that joins roster, recruiting, stats, and scouting data into a single queryable entity.

**Architecture:** The `scouting.player_mart` materialized view provides cfb-app with a single table to query for all player data. It refreshes nightly via pg_cron.

---

## Task 1: Explore Data Sources

**Purpose:** Verify available columns and join keys before building the mart.

**Step 1: Check core.roster columns**
```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'core' AND table_name = 'roster';
```

**Step 2: Check recruiting.recruits columns**
```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'recruiting' AND table_name = 'recruits';
```

**Step 3: Check scouting.players columns**
```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'scouting' AND table_name = 'players';
```

**Step 4: Check stats.player_season_stats columns**
```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'stats' AND table_name = 'player_season_stats';
```

---

## Task 2: Create Player Mart Migration

**Files:**
- Create: `src/storage/migrations/004_player_mart.sql`

**Step 1: Create migration file with materialized view**

The view joins:
- core.roster (canonical player identity)
- recruiting.recruits (recruiting data via athlete_id)
- scouting.players (scouting grades/traits via roster_player_id)
- scouting.transfer_events (portal status)

Note: Stats will be added in Phase 6D (requires aggregation logic).

**Step 2: Apply migration via Supabase MCP**

**Step 3: Verify view exists and has data**

**Step 4: Commit**

---

## Task 3: Add Indexes for Query Patterns

**Files:**
- Create: `src/storage/migrations/005_player_mart_indexes.sql`

**Indexes needed:**
- player_id (primary lookup)
- team (team roster queries)
- position (position filtering)
- portal_status (portal tracker)
- composite_grade (ranking queries)

**Step 1: Create migration with indexes**

**Step 2: Apply migration**

**Step 3: Verify indexes exist**

**Step 4: Commit**

---

## Task 4: Create Refresh Function

**Files:**
- Create: `src/storage/migrations/006_player_mart_refresh.sql`

**Step 1: Create function to refresh the mat view**

```sql
CREATE OR REPLACE FUNCTION scouting.refresh_player_mart()
RETURNS void AS $$
BEGIN
  REFRESH MATERIALIZED VIEW CONCURRENTLY scouting.player_mart;
END;
$$ LANGUAGE plpgsql;
```

**Step 2: Apply migration**

**Step 3: Test refresh function**

**Step 4: Commit**

---

## Task 5: Set Up pg_cron (if available)

**Step 1: Check if pg_cron extension is enabled**

**Step 2: If available, schedule nightly refresh at 7:30 AM CT**

```sql
SELECT cron.schedule(
  'refresh-player-mart',
  '30 13 * * *',  -- 7:30 AM CT = 13:30 UTC
  $$SELECT scouting.refresh_player_mart()$$
);
```

**Step 3: Verify job is scheduled**

---

## Task 6: Update README

**Step 1: Add Phase 6B status section**

**Step 2: Document player_mart schema**

**Step 3: Commit**

---

## Summary

After completing all tasks:

1. **player_mart view** - Unified player entity with roster, recruiting, scouting data
2. **Indexes** - Optimized for team/position/portal queries
3. **Refresh function** - Can be called manually or via cron
4. **pg_cron job** - Nightly refresh at 7:30 AM CT (if available)

**Next:** Phase 6C (Enhanced Matching) - Update player_matching.py with 3-tier system

#!/usr/bin/env python3
"""Backfill player embeddings for existing roster data.

Usage:
    python scripts/backfill_embeddings.py --year 2025 --batch-size 100
    python scripts/backfill_embeddings.py --year 2025 --dry-run
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.processing.embeddings import build_identity_text, generate_embedding
from src.storage.db import get_connection, upsert_player_embedding

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Rate limiting: OpenAI allows 3000 RPM for text-embedding-3-small
REQUESTS_PER_MINUTE = 2500
DELAY_BETWEEN_BATCHES = 60 / (REQUESTS_PER_MINUTE / 100)  # seconds


def get_roster_players_without_embeddings(
    conn,
    year: int,
    limit: int = 1000,
) -> list[dict]:
    """Get roster players that don't have embeddings yet."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            r.id,
            r.first_name || ' ' || r.last_name as name,
            r.team,
            r.position,
            r.year,
            r.home_city || ', ' || r.home_state as hometown
        FROM core.roster r
        LEFT JOIN scouting.player_embeddings pe ON r.id::text = pe.roster_id
        WHERE r.year = %s
        AND pe.id IS NULL
        ORDER BY r.team, r.last_name
        LIMIT %s
        """,
        (year, limit),
    )
    columns = [desc[0] for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def backfill_embeddings(
    year: int,
    batch_size: int = 100,
    dry_run: bool = False,
) -> dict:
    """Backfill embeddings for roster players.

    Args:
        year: Roster year to process
        batch_size: Players per batch
        dry_run: If True, don't actually insert

    Returns:
        Stats dict with processed, skipped, errors counts
    """
    stats = {"processed": 0, "skipped": 0, "errors": 0}

    conn = get_connection()

    try:
        while True:
            players = get_roster_players_without_embeddings(conn, year, batch_size)

            if not players:
                logger.info("No more players to process")
                break

            logger.info(f"Processing batch of {len(players)} players")

            for player in players:
                try:
                    # Build identity text
                    identity_text = build_identity_text({
                        "name": player["name"],
                        "position": player["position"],
                        "team": player["team"],
                        "year": player["year"],
                        "hometown": player["hometown"] if player["hometown"] != ", " else None,
                    })

                    if dry_run:
                        logger.info(f"[DRY RUN] Would embed: {identity_text}")
                        stats["processed"] += 1
                        continue

                    # Generate embedding
                    result = generate_embedding(identity_text)

                    # Store in database
                    upsert_player_embedding(
                        conn=conn,
                        roster_id=str(player["id"]),
                        identity_text=result.identity_text,
                        embedding=result.embedding,
                    )

                    stats["processed"] += 1

                    if stats["processed"] % 100 == 0:
                        logger.info(f"Processed {stats['processed']} players")

                except Exception as e:
                    logger.error(f"Error processing {player['name']}: {e}")
                    stats["errors"] += 1

            # In dry run mode, only run one batch to preview
            if dry_run:
                logger.info("[DRY RUN] Stopping after one batch preview")
                break

            # Rate limiting between batches
            if len(players) == batch_size:
                logger.info(f"Sleeping {DELAY_BETWEEN_BATCHES:.1f}s for rate limiting")
                time.sleep(DELAY_BETWEEN_BATCHES)

    finally:
        conn.close()

    return stats


def main():
    parser = argparse.ArgumentParser(description="Backfill player embeddings")
    parser.add_argument("--year", type=int, default=2025, help="Roster year")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size")
    parser.add_argument("--dry-run", action="store_true", help="Don't insert")
    args = parser.parse_args()

    if not args.dry_run and not os.environ.get("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY not set (required for non-dry-run mode)")
        sys.exit(1)

    logger.info(f"Starting backfill for year {args.year}")
    stats = backfill_embeddings(
        year=args.year,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
    )

    logger.info(f"Completed: {stats}")


if __name__ == "__main__":
    main()

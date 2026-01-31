#!/usr/bin/env python3
# scripts/run_pipeline.py
"""Run the CFB Scout pipeline."""

import argparse
import logging
import sys

from dotenv import load_dotenv

load_dotenv()

from src.processing.pipeline import process_reports
from src.storage.db import get_connection, insert_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def seed_test_data():
    """Seed some test data for development."""
    conn = get_connection()

    test_reports = [
        {
            "source_url": "https://example.com/texas-qb-update",
            "source_name": "manual",
            "content_type": "article",
            "raw_text": """Texas QB Arch Manning continues to impress in spring practice.
            The sophomore signal-caller has shown tremendous growth in his second year,
            displaying improved pocket presence and decision-making. Coaches are excited
            about his development and believe he's ready to lead the offense.""",
            "team_ids": ["Texas"],
        },
        {
            "source_url": "https://example.com/ohio-state-transfer",
            "source_name": "manual",
            "content_type": "article",
            "raw_text": """Ohio State loses another key player to the transfer portal.
            Starting linebacker announces departure amid concerns about playing time.
            This marks the third defensive starter to leave this offseason, raising
            questions about depth heading into the season.""",
            "team_ids": ["Ohio State"],
        },
        {
            "source_url": "https://example.com/georgia-recruiting",
            "source_name": "manual",
            "content_type": "article",
            "raw_text": """Georgia lands another 5-star recruit, continuing their
            dominant recruiting run. The Bulldogs now have the top-ranked class
            for the third consecutive year. Kirby Smart's program shows no signs
            of slowing down on the recruiting trail.""",
            "team_ids": ["Georgia"],
        },
    ]

    inserted = 0
    for report in test_reports:
        try:
            report_id = insert_report(conn, **report)
            logger.info(f"Inserted test report {report_id}: {report['source_url']}")
            inserted += 1
        except Exception as e:
            logger.warning(f"Skipping (likely duplicate): {e}")

    conn.close()
    logger.info(f"Seeded {inserted} test reports")


def main():
    parser = argparse.ArgumentParser(description="Run CFB Scout pipeline")
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Seed test data for development",
    )
    parser.add_argument(
        "--process",
        action="store_true",
        help="Process unprocessed reports",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run full pipeline (seed + process)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of reports to process per batch",
    )

    args = parser.parse_args()

    if not any([args.seed, args.process, args.all]):
        parser.print_help()
        sys.exit(1)

    if args.seed or args.all:
        logger.info("Seeding test data...")
        seed_test_data()

    if args.process or args.all:
        logger.info("Processing reports...")
        result = process_reports(batch_size=args.batch_size)
        logger.info(f"Processing complete: {result['processed']}/{result['total']} reports")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# scripts/run_pipeline.py
"""Run the CFB Scout pipeline."""

import argparse
import logging
import sys

from dotenv import load_dotenv

load_dotenv()

from src.crawlers.recruiting.two47 import Two47Crawler
from src.processing.entity_linking import run_entity_linking
from src.processing.grading import run_grading_pipeline
from src.processing.pipeline import process_reports
from src.storage.db import (
    get_connection,
    get_pending_links,
    insert_report,
    update_pending_link_status,
)

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


def review_pending_links():
    """Interactive review of pending player links."""
    conn = get_connection()
    try:
        pending = get_pending_links(conn, status="pending", limit=50)
        print(f"\n{len(pending)} pending links to review\n")

        for link in pending:
            print(f"ID: {link['id']}")
            print(f"  Source: {link['source_name']} ({link['source_team']})")
            print(f"  Candidate: roster_id={link['candidate_roster_id']}")
            print(f"  Score: {link['match_score']:.2%} ({link['match_method']})")
            print(f"  Context: {link['source_context']}")

            action = input("\n  [a]pprove / [r]eject / [s]kip / [q]uit: ").lower()

            if action == "a":
                update_pending_link_status(conn, link["id"], "approved")
                print("  -> Approved")
            elif action == "r":
                update_pending_link_status(conn, link["id"], "rejected")
                print("  -> Rejected")
            elif action == "q":
                break
            else:
                print("  -> Skipped")

            print()
    finally:
        conn.close()


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
    parser.add_argument(
        "--crawl-247",
        action="store_true",
        help="Crawl 247Sports for recruiting data",
    )
    parser.add_argument(
        "--link",
        action="store_true",
        help="Run entity linking on processed reports",
    )
    parser.add_argument(
        "--teams",
        nargs="+",
        default=["texas"],
        help="Teams to crawl (default: texas)",
    )
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=[2025],
        help="Years to crawl (default: 2025)",
    )
    parser.add_argument(
        "--grade",
        action="store_true",
        help="Run grading pipeline to update player grades",
    )
    parser.add_argument(
        "--review-links",
        action="store_true",
        help="Review pending player links",
    )

    args = parser.parse_args()

    if not any(
        [
            args.seed,
            args.process,
            args.all,
            args.crawl_247,
            args.link,
            args.grade,
            args.review_links,
        ]
    ):
        parser.print_help()
        sys.exit(1)

    if args.seed or args.all:
        logger.info("Seeding test data...")
        seed_test_data()

    if args.crawl_247 or args.all:
        logger.info("Crawling 247Sports...")
        crawler = Two47Crawler(teams=args.teams, years=args.years)
        result = crawler.crawl()
        logger.info(f"247 crawl complete: {result.records_new} new records")

    if args.process or args.all:
        logger.info("Processing reports...")
        result = process_reports(batch_size=args.batch_size)
        logger.info(f"Processing complete: {result['processed']}/{result['total']} reports")

    if args.link or args.all:
        logger.info("Running entity linking...")
        result = run_entity_linking(batch_size=args.batch_size)
        logger.info(f"Entity linking complete: {result['players_linked']} players linked")

    if args.grade or args.all:
        logger.info("Running grading pipeline...")
        result = run_grading_pipeline(batch_size=args.batch_size)
        logger.info(f"Grading complete: {result['players_updated']} players updated")

    if args.review_links:
        logger.info("Starting pending links review...")
        review_pending_links()


if __name__ == "__main__":
    main()

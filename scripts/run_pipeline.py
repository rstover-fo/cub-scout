#!/usr/bin/env python3
# scripts/run_pipeline.py
"""Run the CFB Scout pipeline."""

import argparse
import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

from src.crawlers.recruiting.two47 import Two47Crawler
from src.processing.alerting import run_alert_check
from src.processing.entity_linking import run_entity_linking
from src.processing.grading import run_grading_pipeline
from src.processing.pff_pipeline import run_pff_pipeline
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


@dataclass
class StageResult:
    stage: str
    status: str  # "ok", "error", "skipped"
    records: int = 0
    errors: int = 0
    duration_seconds: float = 0.0


async def run_stage(name: str, coro) -> StageResult:
    """Run a pipeline stage with timing and error capture."""
    start = time.monotonic()
    try:
        result = await coro
        duration = time.monotonic() - start
        # Extract counts — handle both dicts and CrawlResult dataclass
        if isinstance(result, dict):
            records = (
                result.get("records_new", 0)
                or result.get("processed", 0)
                or result.get("players_updated", 0)
                or result.get("alerts_fired", 0)
                or 0
            )
            errors = result.get("errors", 0) or 0
        elif hasattr(result, "records_new"):
            records = result.records_new or 0
            errors = len(result.errors) if hasattr(result, "errors") else 0
        else:
            records = 0
            errors = 0
        return StageResult(
            stage=name,
            status="ok",
            records=records,
            errors=errors,
            duration_seconds=round(duration, 2),
        )
    except Exception as e:
        duration = time.monotonic() - start
        logger.error(f"Stage {name} failed: {e}")
        return StageResult(stage=name, status="error", duration_seconds=round(duration, 2))


def _log_stage(sr: StageResult) -> None:
    """Emit structured JSON log for a completed stage."""
    logger.info(
        json.dumps(
            {
                "stage": sr.stage,
                "status": sr.status,
                "records": sr.records,
                "errors": sr.errors,
                "duration_s": sr.duration_seconds,
            }
        )
    )


async def seed_test_data():
    """Seed some test data for development."""
    async with get_connection() as conn:
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
                report_id = await insert_report(conn, **report)
                logger.info(f"Inserted test report {report_id}: {report['source_url']}")
                inserted += 1
            except Exception as e:
                logger.warning(f"Skipping (likely duplicate): {e}")

    logger.info(f"Seeded {inserted} test reports")


async def review_pending_links():
    """Interactive review of pending player links."""
    async with get_connection() as conn:
        pending = await get_pending_links(conn, status="pending", limit=50)
        print(f"\n{len(pending)} pending links to review\n")

        for link in pending:
            print(f"ID: {link['id']}")
            print(f"  Source: {link['source_name']} ({link['source_team']})")
            print(f"  Candidate: roster_id={link['candidate_roster_id']}")
            print(f"  Score: {link['match_score']:.2%} ({link['match_method']})")
            print(f"  Context: {link['source_context']}")

            action = input("\n  [a]pprove / [r]eject / [s]kip / [q]uit: ").lower()

            if action == "a":
                await update_pending_link_status(conn, link["id"], "approved")
                print("  -> Approved")
            elif action == "r":
                await update_pending_link_status(conn, link["id"], "rejected")
                print("  -> Rejected")
            elif action == "q":
                break
            else:
                print("  -> Skipped")

            print()


async def async_main():
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
    parser.add_argument(
        "--fetch-pff",
        action="store_true",
        help="Fetch PFF grades for players missing recent data",
    )
    parser.add_argument(
        "--evaluate-alerts",
        action="store_true",
        help="Evaluate alert conditions for all players with active alerts",
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
            args.fetch_pff,
            args.review_links,
            args.evaluate_alerts,
        ]
    ):
        parser.print_help()
        sys.exit(1)

    stage_results: list[StageResult] = []

    if args.seed or args.all:
        logger.info("Seeding test data...")
        sr = await run_stage("seed", seed_test_data())
        stage_results.append(sr)
        _log_stage(sr)

    if args.crawl_247 or args.all:
        logger.info("Crawling 247Sports...")
        crawler = Two47Crawler(teams=args.teams, years=args.years)
        sr = await run_stage("crawl-247", crawler.crawl())
        stage_results.append(sr)
        _log_stage(sr)

    if args.process or args.all:
        logger.info("Processing reports...")
        sr = await run_stage("process", process_reports(batch_size=args.batch_size))
        stage_results.append(sr)
        _log_stage(sr)

    if args.link or args.all:
        logger.info("Running entity linking...")
        sr = await run_stage("link", run_entity_linking(batch_size=args.batch_size))
        stage_results.append(sr)
        _log_stage(sr)

    if args.grade or args.all:
        logger.info("Running grading pipeline...")
        sr = await run_stage("grade", run_grading_pipeline(batch_size=args.batch_size))
        stage_results.append(sr)
        _log_stage(sr)

    if args.fetch_pff or args.all:
        logger.info("Fetching PFF grades...")
        sr = await run_stage("fetch-pff", run_pff_pipeline(batch_size=args.batch_size))
        stage_results.append(sr)
        _log_stage(sr)

    if args.evaluate_alerts or args.all:
        sr = await run_stage("evaluate-alerts", run_alert_check())
        stage_results.append(sr)
        _log_stage(sr)

    if args.review_links:
        logger.info("Starting pending links review...")
        await review_pending_links()

    # Pipeline summary
    if stage_results:
        total_time = sum(sr.duration_seconds for sr in stage_results)
        failed = sum(1 for sr in stage_results if sr.status == "error")
        logger.info(
            json.dumps(
                {
                    "pipeline_summary": True,
                    "stages_run": len(stage_results),
                    "stages_failed": failed,
                    "total_duration_s": round(total_time, 2),
                }
            )
        )
        if failed > 0:
            sys.exit(1)


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()

"""Processing pipeline to summarize crawled reports."""

import logging
from datetime import datetime

from ..storage.db import get_connection, get_unprocessed_reports, mark_report_processed
from .summarizer import summarize_report

logger = logging.getLogger(__name__)


async def process_reports(batch_size: int = 50) -> dict:
    """Process unprocessed reports through Claude summarization.

    Args:
        batch_size: Number of reports to process in this run.

    Returns:
        Dict with processing stats.
    """
    async with get_connection() as conn:
        reports = await get_unprocessed_reports(conn, limit=batch_size)
        logger.info(f"Found {len(reports)} unprocessed reports")

        processed = 0
        errors = 0

        for report in reports:
            try:
                result = summarize_report(
                    text=report["raw_text"],
                    team_context=report["team_ids"],
                )

                await mark_report_processed(
                    conn,
                    report_id=report["id"],
                    summary=result["summary"],
                    sentiment_score=result["sentiment_score"],
                )

                processed += 1
                logger.debug(f"Processed report {report['id']}")

            except Exception as e:
                errors += 1
                logger.error(f"Error processing report {report['id']}: {e}")

        return {
            "total": len(reports),
            "processed": processed,
            "errors": errors,
            "timestamp": datetime.now().isoformat(),
        }

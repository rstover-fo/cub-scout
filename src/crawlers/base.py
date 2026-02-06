"""Base crawler class for CFB Scout."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class CrawlResult:
    """Result of a crawl operation."""

    source_name: str
    records_crawled: int
    records_new: int
    errors: list[str] = field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @property
    def duration_seconds(self) -> float | None:
        """Duration of crawl in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class BaseCrawler(ABC):
    """Abstract base class for crawlers."""

    source_name: str = "unknown"

    @abstractmethod
    async def crawl(self) -> CrawlResult:
        """Execute the crawl and return results."""
        pass

    def log_start(self) -> datetime:
        """Log crawl start and return timestamp."""
        started = datetime.now()
        logger.info(f"Starting {self.source_name} crawl at {started}")
        return started

    def log_complete(self, result: CrawlResult) -> None:
        """Log crawl completion."""
        duration = result.duration_seconds
        logger.info(
            f"Completed {self.source_name} crawl: "
            f"{result.records_new}/{result.records_crawled} new records "
            f"in {duration:.1f}s"
            if duration
            else ""
        )
        if result.errors:
            logger.warning(f"Errors during crawl: {len(result.errors)}")

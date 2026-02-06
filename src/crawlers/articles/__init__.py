"""Article crawlers for scouting content."""

from .base import ArticleContent, ArticleCrawlerBase, ArticleLink
from .on3_articles import On3ArticleCrawler
from .two47_articles import Two47ArticleCrawler

__all__ = [
    "ArticleCrawlerBase",
    "ArticleContent",
    "ArticleLink",
    "On3ArticleCrawler",
    "Two47ArticleCrawler",
]

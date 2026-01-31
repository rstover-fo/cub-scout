"""Configuration management for CFB Scout."""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    """Application configuration."""

    # Supabase
    database_url: str

    # Reddit
    reddit_client_id: str
    reddit_client_secret: str
    reddit_user_agent: str

    # Anthropic
    anthropic_api_key: str

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        return cls(
            database_url=os.environ["DATABASE_URL"],
            reddit_client_id=os.environ["REDDIT_CLIENT_ID"],
            reddit_client_secret=os.environ["REDDIT_CLIENT_SECRET"],
            reddit_user_agent=os.environ.get("REDDIT_USER_AGENT", "cfb-scout:v0.1.0"),
            anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        )


def get_config() -> Config:
    """Get application configuration."""
    return Config.from_env()

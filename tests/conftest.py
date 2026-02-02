"""Pytest configuration for cfb-scout tests."""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Load .env from project root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)


@pytest.fixture
def mock_db_connection():
    """Provide a database connection for tests.

    Uses real database - tests that modify data should clean up.
    """
    from src.storage.db import get_connection

    conn = get_connection()
    yield conn
    conn.close()

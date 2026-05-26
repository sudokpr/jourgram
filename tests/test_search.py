"""Tests for search module."""

import pytest
from datetime import datetime

from app.search.engine import SearchEngine, SearchIndexer


@pytest.mark.asyncio
async def test_search_engine_init(tmp_path):
    """Test search engine initialization."""
    from app.config.settings import Settings

    settings = Settings()
    settings.storage.data_dir = tmp_path

    engine = SearchEngine(settings)
    await engine.initialize()

    assert engine._db is not None
"""Tests for summarizer module."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.summarizer.daily import DailySummarizer, WeeklySummarizer


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = MagicMock()
    settings.storage.data_dir = "/tmp/test_data"
    settings.storage.raw_json_dir = "/tmp/test_raw"
    settings.gemini.api_key = "test_key"
    settings.gemini.model_daily = "gemini-2.5-flash"
    return settings


def test_daily_summarizer_init(mock_settings):
    """Test daily summarizer initialization."""
    summarizer = DailySummarizer(mock_settings)
    assert summarizer.settings == mock_settings
    assert summarizer._db is None


def test_group_by_topic():
    """Test grouping messages by topic."""
    summarizer = DailySummarizer(MagicMock())

    messages = [
        {"topic_id": 1, "text": "msg1"},
        {"topic_id": 2, "text": "msg2"},
        {"topic_id": 1, "text": "msg3"},
    ]

    grouped = summarizer._group_by_topic(messages)
    assert len(grouped[1]) == 2
    assert len(grouped[2]) == 1


@pytest.mark.asyncio
async def test_daily_summarizer_no_messages(mock_settings):
    """Test summarizer handles no messages gracefully."""
    from app.storage.database import Database

    mock_settings.storage.data_dir.mkdir = MagicMock()

    summarizer = DailySummarizer(mock_settings)

    with patch.object(summarizer, "_get_messages_for_date", return_value=[]):
        result = await summarizer.summarize_date("2024-01-15")
        assert result["content"] == "No messages found for this date."
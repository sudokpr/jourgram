"""Tests for models module."""

import pytest
from datetime import datetime

from app.models import (
    NormalizedMessage,
    MediaInfo,
    LinkInfo,
    DailySummary,
    ProcessingJob,
)


def test_normalized_message_model():
    """Test normalized message model."""
    msg = NormalizedMessage(
        event_id=1,
        chat_id=123,
        topic_id=1,
        message_id=456,
        text="Test message",
        sender_name="John",
        timestamp=datetime.now(),
    )
    assert msg.text == "Test message"
    assert msg.sender_name == "John"
    assert msg.has_urls is False


def test_media_info_model():
    """Test media info model."""
    media = MediaInfo(
        event_id=1,
        normalized_message_id=1,
        file_type="photo",
        local_path="/path/to/file.jpg",
    )
    assert media.file_type == "photo"
    assert media.mime_type is None


def test_link_info_model():
    """Test link info model."""
    link = LinkInfo(
        url="https://example.com",
        title="Example",
        domain="example.com",
    )
    assert link.url == "https://example.com"
    assert link.domain == "example.com"


def test_processing_job_model():
    """Test processing job model."""
    job = ProcessingJob(
        job_type="normalize",
        event_id=123,
        priority=1,
        payload={"chat_id": 1, "message_id": 123},
    )
    assert job.job_type == "normalize"
    assert job.payload["chat_id"] == 1
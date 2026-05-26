"""Pydantic models for data validation."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TelegramMessage(BaseModel):
    """Raw Telegram message model."""

    id: int
    peer_id: int
    date: datetime
    message: str | None = None
    out: bool = False
    mentioned: bool = False
    media_unread: bool = False
    silent: bool = False
    post: bool = False
    from_scheduled: bool = False
    edit_hide: bool = False
    pinned: bool = False
    from_id: int | None = None
    fwd_from: dict | None = None
    via_bot_id: int | None = None
    reply_to: dict | None = None
    entities: list[dict] | None = None
    reply_markup: dict | None = None
    ttl_period: int | None = None
    group_metadata: dict | None = None


class ChatInfo(BaseModel):
    """Chat information model."""

    id: int
    title: str
    type: str
    username: str | None = None
    participants_count: int | None = None


class TopicInfo(BaseModel):
    """Topic information model."""

    id: int
    chat_id: int
    thread_id: int
    title: str | None = None


class NormalizedMessage(BaseModel):
    """Normalized message model for internal processing."""

    event_id: int
    chat_id: int
    topic_id: int | None
    message_id: int
    text: str | None
    raw_text: str | None
    sender_id: int | None
    sender_name: str | None
    timestamp: datetime
    edited_at: datetime | None
    is_forwarded: bool = False
    forwarded_from_chat_id: int | None = None
    forwarded_from_message_id: int | None = None
    reply_to_message_id: int | None = None
    has_media: bool = False
    media_type: str | None = None
    has_urls: bool = False
    url_count: int = 0


class MediaInfo(BaseModel):
    """Media information model."""

    event_id: int
    normalized_message_id: int
    file_type: str
    file_name: str | None = None
    file_size: int | None = None
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    duration: int | None = None
    local_path: str | None = None
    remote_url: str | None = None
    caption: str | None = None


class LinkInfo(BaseModel):
    """Link information model."""

    url: str
    canonical_url: str | None = None
    title: str | None = None
    source: str | None = None
    domain: str | None = None


class DailySummary(BaseModel):
    """Daily summary model."""

    date: str
    content: str
    topics_summary: dict[str, str] | None = None
    metrics: dict[str, Any] | None = None


class WeeklySummary(BaseModel):
    """Weekly summary model."""

    week_start: str
    week_end: str
    content: str
    daily_summaries: list[DailySummary] | None = None
    metrics: dict[str, Any] | None = None


class ProcessingJob(BaseModel):
    """Processing job model."""

    job_type: str
    event_id: int | None = None
    priority: int = 0
    payload: dict | None = None


class HealthStatus(BaseModel):
    """Health check status model."""

    healthy: bool
    components: dict[str, dict[str, Any]]
    issues: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    """Search result model."""

    message_id: int
    chat_id: int
    topic_id: int | None
    text: str
    sender_name: str | None
    timestamp: datetime
    score: float | None = None
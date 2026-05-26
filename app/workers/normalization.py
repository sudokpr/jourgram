"""Normalization worker - processes raw events into normalized messages."""

from __future__ import annotations

import json
import re
from datetime import datetime

import structlog

from app.config.settings import Settings
from app.storage import Database

logger = structlog.get_logger(__name__)


class NormalizationWorker:
    """Worker that normalizes raw Telegram events into structured messages."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._db: Database | None = None

    async def initialize(self) -> None:
        """Initialize the worker."""
        self._db = Database(self.settings)
        await self._db.initialize()

    async def process_pending(self) -> int:
        """Process pending normalization jobs."""
        if not self._db:
            await self.initialize()

        processed = 0
        async with self._db.get_connection() as conn:
            cursor = await conn.execute(
                """SELECT id, payload FROM processing_jobs WHERE status = 'pending' AND job_type = 'normalize' ORDER BY priority DESC, created_at ASC LIMIT ?""",
                (self.settings.processing.batch_size,),
            )
            jobs = await cursor.fetchall()

        for job in jobs:
            try:
                await self._process_job(job)
                processed += 1
            except Exception as e:
                logger.error("normalization_job_failed", job_id=job[0], error=str(e))
                await self._mark_job_failed(job[0], str(e))

        return processed

    async def _process_job(self, job: tuple) -> None:
        """Process a single normalization job."""
        job_id, payload_str = job
        payload = json.loads(payload_str)

        chat_id = payload["chat_id"]
        message_id = payload["message_id"]
        topic_id = payload.get("topic_id")

        raw_json = await self._load_raw_json(chat_id, message_id)
        if not raw_json:
            logger.warning("raw_json_not_found", chat_id=chat_id, message_id=message_id)
            await self._mark_job_completed(job_id)
            return

        normalized = await self._normalize(raw_json)

        await self._store_normalized(normalized)

        await self._create_media_job_if_needed(normalized)

        await self._create_link_job_if_needed(normalized)

        await self._mark_job_completed(job_id)

    async def _load_raw_json(self, chat_id: int, message_id: int) -> dict | None:
        """Load raw JSON from filesystem."""
        from pathlib import Path

        date_str = ""
        if "date" in self.settings.storage.raw_json_dir:
            date_parts = self.settings.storage.raw_json_dir.parts
            date_str = ""

        for year in range(2020, 2030):
            for month in range(1, 13):
                for day in range(1, 32):
                    check_path = self.settings.storage.raw_json_dir / str(year) / f"{month:02d}" / f"{day:02d}" / f"{chat_id}_{message_id}.json"
                    if check_path.exists():
                        with open(check_path) as f:
                            return json.load(f)

        return None

    async def _normalize(self, raw: dict) -> dict:
        """Normalize raw message data."""
        text = raw.get("message", "") or raw.get("text", "") or ""

        urls = raw.get("urls", []) or []
        if isinstance(urls, str):
            urls = json.loads(urls)

        has_urls = len(urls) > 0

        return {
            "event_id": raw.get("event_id", 0),
            "chat_id": raw.get("chat_id", 0),
            "topic_id": raw.get("topic_id"),
            "message_id": raw.get("id", 0),
            "text": text,
            "raw_text": raw.get("raw_text"),
            "sender_id": raw.get("from_id"),
            "sender_name": raw.get("sender_name"),
            "timestamp": datetime.fromisoformat(raw["date"]) if "date" in raw else datetime.now(),
            "edited_at": datetime.fromisoformat(raw["edit_date"]) if raw.get("edit_date") else None,
            "is_forwarded": raw.get("fwd_from") is not None,
            "forwarded_from_chat_id": raw.get("fwd_from", {}).get("from_id"),
            "forwarded_from_message_id": raw.get("fwd_from", {}).get("message_id"),
            "reply_to_message_id": raw.get("reply_to", {}).get("reply_to_msg_id") if isinstance(raw.get("reply_to"), dict) else None,
            "has_media": raw.get("media", {}).get("has_media", False) if isinstance(raw.get("media"), dict) else False,
            "media_type": raw.get("media", {}).get("media_type") if isinstance(raw.get("media"), dict) else None,
            "has_urls": has_urls,
            "url_count": len(urls),
        }

    async def _store_normalized(self, normalized: dict) -> None:
        """Store normalized message in database."""
        if not self._db:
            return

        async with self._db.get_connection() as conn:
            await conn.execute(
                """INSERT OR REPLACE INTO normalized_messages 
                (event_id, chat_id, topic_id, message_id, text, raw_text, sender_id, sender_name, 
                timestamp, edited_at, is_forwarded, forwarded_from_chat_id, forwarded_from_message_id,
                reply_to_message_id, has_media, media_type, has_urls, url_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    normalized["event_id"],
                    normalized["chat_id"],
                    normalized["topic_id"],
                    normalized["message_id"],
                    normalized["text"],
                    normalized["raw_text"],
                    normalized["sender_id"],
                    normalized["sender_name"],
                    normalized["timestamp"].isoformat() if isinstance(normalized["timestamp"], datetime) else normalized["timestamp"],
                    normalized["edited_at"].isoformat() if normalized["edited_at"] else None,
                    normalized["is_forwarded"],
                    normalized["forwarded_from_chat_id"],
                    normalized["forwarded_from_message_id"],
                    normalized["reply_to_message_id"],
                    normalized["has_media"],
                    normalized["media_type"],
                    normalized["has_urls"],
                    normalized["url_count"],
                ),
            )
            await conn.commit()

    async def _create_media_job_if_needed(self, normalized: dict) -> None:
        """Create a media processing job if message has media."""
        if not normalized["has_media"] or not self._db:
            return

        async with self._db.get_connection() as conn:
            await conn.execute(
                """INSERT INTO processing_jobs (job_type, event_id, status, payload, priority) VALUES (?, ?, ?, ?, ?)""",
                (
                    "download_media",
                    normalized["event_id"],
                    "pending",
                    json.dumps({
                        "chat_id": normalized["chat_id"],
                        "message_id": normalized["message_id"],
                        "media_type": normalized["media_type"],
                    }),
                    2,
                ),
            )
            await conn.commit()

    async def _create_link_job_if_needed(self, normalized: dict) -> None:
        """Create a link processing job if message has URLs."""
        if not normalized["has_urls"] or not self._db:
            return

        import json

        async with self._db.get_connection() as conn:
            await conn.execute(
                """INSERT INTO processing_jobs (job_type, event_id, status, payload, priority) VALUES (?, ?, ?, ?, ?)""",
                (
                    "fetch_link",
                    normalized["event_id"],
                    "pending",
                    json.dumps({
                        "chat_id": normalized["chat_id"],
                        "message_id": normalized["message_id"],
                        "url_count": normalized["url_count"],
                    }),
                    1,
                ),
            )
            await conn.commit()

    async def _mark_job_completed(self, job_id: int) -> None:
        """Mark a job as completed."""
        if not self._db:
            return

        async with self._db.get_connection() as conn:
            await conn.execute(
                """UPDATE processing_jobs SET status = 'completed', completed_at = CURRENT_TIMESTAMP WHERE id = ?""",
                (job_id,),
            )
            await conn.commit()

    async def _mark_job_failed(self, job_id: int, error: str) -> None:
        """Mark a job as failed."""
        if not self._db:
            return

        async with self._db.get_connection() as conn:
            await conn.execute(
                """UPDATE processing_jobs SET status = 'failed', error = ?, attempts = attempts + 1 WHERE id = ?""",
                (error, job_id),
            )
            await conn.commit()
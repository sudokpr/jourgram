"""Media download worker."""

from __future__ import annotations

import json
from pathlib import Path

import aiohttp
import structlog

from app.config.settings import Settings
from app.storage import Database, MediaStorage

logger = structlog.get_logger(__name__)


class MediaDownloadWorker:
    """Worker that downloads media from Telegram messages."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._db: Database | None = None
        self._media_storage: MediaStorage | None = None

    async def initialize(self) -> None:
        """Initialize the worker."""
        self._db = Database(self.settings)
        await self._db.initialize()
        self._media_storage = MediaStorage(self.settings.storage.media_dir)

    async def process_pending(self) -> int:
        """Process pending media download jobs."""
        if not self._db:
            await self.initialize()

        processed = 0
        async with self._db.get_connection() as conn:
            cursor = await conn.execute(
                """SELECT id, payload FROM processing_jobs WHERE status = 'pending' AND job_type = 'download_media' ORDER BY priority DESC, created_at ASC LIMIT ?""",
                (self.settings.processing.batch_size,),
            )
            jobs = await cursor.fetchall()

        for job in jobs:
            try:
                await self._process_job(job)
                processed += 1
            except Exception as e:
                logger.error("media_download_job_failed", job_id=job[0], error=str(e))
                await self._mark_job_failed(job[0], str(e))

        return processed

    async def _process_job(self, job: tuple) -> None:
        """Process a single media download job."""
        job_id, payload_str = job
        payload = json.loads(payload_str)

        chat_id = payload["chat_id"]
        message_id = payload["message_id"]
        media_type = payload.get("media_type")

        normalized_id = await self._get_normalized_id(chat_id, message_id)
        if not normalized_id:
            await self._mark_job_completed(job_id)
            return

        from app.telegram.client import TelegramClientManager

        try:
            client = TelegramClientManager(self.settings)
            await client.start()

            message = await client.client.get_messages(chat_id, ids=[message_id])
            if message and message[0].media:
                local_path = await self._download_media(message[0], chat_id, message_id)
                await self._store_media_info(normalized_id, local_path, media_type)

            await client.stop()

        except Exception as e:
            logger.error("media_fetch_error", chat_id=chat_id, message_id=message_id, error=str(e))

        await self._mark_job_completed(job_id)

    async def _download_media(self, message: Any, chat_id: int, message_id: int) -> Path | None:
        """Download media from message."""
        if not hasattr(message.media, "photo"):
            return None

        photo = message.media.photo
        largest = max(photo.sizes, key=lambda s: getattr(s, "size", 0)) if photo.sizes else None

        if not largest or not hasattr(largest, "bytes"):
            return None

        file_name = f"{chat_id}_{message_id}.jpg"
        date_path = self.settings.storage.media_dir / "tmp"

        file_path = date_path / file_name
        date_path.mkdir(parents=True, exist_ok=True)

        with open(file_path, "wb") as f:
            f.write(largest.bytes)

        return file_path

    async def _get_normalized_id(self, chat_id: int, message_id: int) -> int | None:
        """Get normalized message ID."""
        if not self._db:
            return None

        async with self._db.get_connection() as conn:
            cursor = await conn.execute(
                """SELECT id FROM normalized_messages WHERE chat_id = ? AND message_id = ?""",
                (chat_id, message_id),
            )
            row = await cursor.fetchone()
            return row[0] if row else None

    async def _store_media_info(self, normalized_id: int, local_path: Path | None, media_type: str | None) -> None:
        """Store media information in database."""
        if not self._db or not local_path:
            return

        async with self._db.get_connection() as conn:
            await conn.execute(
                """INSERT INTO media (event_id, normalized_message_id, file_type, local_path) VALUES (?, ?, ?, ?)""",
                (0, normalized_id, media_type or "unknown", str(local_path)),
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
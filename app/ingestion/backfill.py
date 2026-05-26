"""Backfill worker for historical messages."""

from __future__ import annotations

from datetime import datetime, timedelta

import structlog

from app.config.settings import Settings
from app.storage import Database

logger = structlog.get_logger(__name__)


class BackfillWorker:
    """Worker to backfill historical messages from Telegram."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._db: Database | None = None

    async def initialize(self) -> None:
        """Initialize the backfill worker."""
        self._db = Database(self.settings)
        await self._db.initialize()

    async def backfill_days(self, days: int) -> None:
        """Backfill messages for specified number of days."""
        await self.initialize()

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        logger.info("backfill_started", start=start_date.isoformat(), end=end_date.isoformat())

        from telethon import TelegramClient

        config = self.settings.telegram
        if not config:
            raise ValueError("Telegram configuration required")

        client = TelegramClient(
            session=config.session_name,
            api_id=config.api_id,
            api_hash=config.api_hash,
        )
        await client.start(phone=config.phone)

        from app.storage.raw_storage import RawJsonStorage

        raw_storage = RawJsonStorage(self.settings.storage.raw_json_dir)

        try:
            async for message in client.iter_messages(
                entity=config.topics.journal if hasattr(config, "topics") and config.topics else None,
                offset_date=end_date,
                reverse=True,
                limit=None,
            ):
                try:
                    payload = await self._extract_message_data(message)
                    await raw_storage.store(message.chat_id, message.id, payload, message.date)
                    logger.debug("backfill_message", message_id=message.id, date=message.date)
                except Exception as e:
                    logger.error("backfill_error", message_id=message.id, error=str(e))

        except Exception as e:
            logger.error("backfill_iteration_error", error=str(e))
        finally:
            await client.disconnect()

        logger.info("backfill_completed", days=days)

    async def _extract_message_data(self, message: Any) -> dict:
        """Extract message data for backfill."""
        from datetime import datetime

        sender_id = None
        sender_name = None
        if hasattr(message, "from_id") and message.from_id:
            sender_id = getattr(message.from_id, "user_id", None) or getattr(message.from_id, "channel_id", None)

        if hasattr(message, "sender") and message.sender:
            sender_name = getattr(message.sender, "first_name", None) or getattr(message.sender, "title", None)

        has_media = hasattr(message, "media") and message.media is not None

        return {
            "id": message.id,
            "chat_id": message.chat_id if hasattr(message, "chat_id") else 0,
            "date": message.date.isoformat() if hasattr(message, "date") else datetime.now().isoformat(),
            "message": getattr(message, "message", None) or getattr(message, "text", None),
            "from_id": sender_id,
            "sender_name": sender_name,
            "has_media": has_media,
            "is_edit": hasattr(message, "edit_date") and message.edit_date is not None,
        }

    async def backfill_date_range(self, start_date: datetime, end_date: datetime) -> None:
        """Backfill messages within a specific date range."""
        logger.info("backfill_range", start=start_date.isoformat(), end=end_date.isoformat())
        pass
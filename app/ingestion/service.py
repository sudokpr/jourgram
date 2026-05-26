"""Ingestion service using Telethon."""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, PhoneMigrateError, NetworkMigrateError

from app.config.settings import Settings
from app.storage import Database, RawJsonStorage

logger = structlog.get_logger(__name__)


class IngestionService:
    """Main ingestion service that listens to Telegram updates."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: TelegramClient | None = None
        self._running = False
        self._db: Database | None = None
        self._raw_storage: RawJsonStorage | None = None

    async def initialize(self) -> None:
        """Initialize the ingestion service."""
        self._db = Database(self.settings)
        await self._db.initialize()
        self._raw_storage = RawJsonStorage(self.settings.storage.raw_json_dir)

        config = self.settings.telegram
        if not config:
            raise ValueError("Telegram configuration required")

        self._client = TelegramClient(
            session=config.session_name,
            api_id=config.api_id,
            api_hash=config.api_hash,
            flood_sleep_threshold=config.flood_sleep_threshold,
        )

        await self._client.start(phone=config.phone)

        # Get the last message ID to start from
        self._last_message_id = 0
        async for msg in self._client.iter_messages(config.chat_id, limit=1):
            self._last_message_id = msg.id

        chats_filter = [config.chat_id] if config.chat_id else []

        self._client.add_event_handler(
            self._handle_new_message,
            events.NewMessage(chats=chats_filter if chats_filter else None)
        )
        self._client.add_event_handler(
            self._handle_message_edit,
            events.MessageEdited(chats=chats_filter if chats_filter else None)
        )

        logger.info("ingestion_service_initialized", chat_id=config.chat_id, last_id=self._last_message_id)

    async def _handle_new_message(self, event: events.NewMessage) -> None:
        """Handle new message events."""
        try:
            if not hasattr(event.message, "message") and not hasattr(event.message, "text"):
                return

            message = event.message
            chat_id = message.chat_id if hasattr(message, "chat_id") else 0

            topic_id = self._extract_topic_id(event, message)

            payload = await self._extract_payload(message, topic_id)

            await self._raw_storage.store(chat_id, message.id, payload, message.date)

            await self._store_event(chat_id, topic_id, message.id, payload)

            await self._queue_processing(chat_id, message.id, topic_id)

            logger.debug(
                "message_ingested",
                chat_id=chat_id,
                topic_id=topic_id,
                message_id=message.id,
            )

        except Exception as e:
            logger.error("ingestion_error", error=str(e), message_id=getattr(event.message, "id", None))

    async def _handle_message_edit(self, event: events.MessageEdited) -> None:
        """Handle message edit events."""
        try:
            message = event.message
            chat_id = message.chat_id if hasattr(message, "chat_id") else 0

            topic_id = self._extract_topic_id(event, message)

            payload = await self._extract_payload(message, topic_id)
            payload["is_edit"] = True

            await self._raw_storage.store(chat_id, message.id, payload, message.date)

            await self._update_event(chat_id, topic_id, message.id, payload)

            logger.debug("message_edit_ingested", chat_id=chat_id, message_id=message.id)

        except Exception as e:
            logger.error("edit_ingestion_error", error=str(e))

    def _extract_topic_id(self, event: events.NewMessage, message: Any) -> int | None:
        """Extract topic/thread ID from message."""
        if hasattr(event, "reply_to_msg_id") and event.reply_to_msg_id:
            return event.reply_to_msg_id

        if hasattr(message, "reply_to"):
            reply_to = message.reply_to
            if hasattr(reply_to, "reply_to_top_id") and reply_to.reply_to_top_id:
                return reply_to.reply_to_top_id
            if hasattr(reply_to, "reply_to_msg_id") and reply_to.reply_to_msg_id:
                return reply_to.reply_to_msg_id

        return None

    async def _extract_payload(self, message: Any, topic_id: int | None) -> dict:
        """Extract message data into a serializable dict."""
        from datetime import datetime

        sender_id = None
        sender_name = None
        if hasattr(message, "from_id") and message.from_id:
            if hasattr(message.from_id, "user_id"):
                sender_id = message.from_id.user_id
            elif hasattr(message.from_id, "channel_id"):
                sender_id = message.from_id.channel_id

        if hasattr(message, "sender") and message.sender:
            sender_name = getattr(message.sender, "first_name", None) or getattr(message.sender, "title", None) or str(sender_id)

        has_media = hasattr(message, "media") and message.media is not None
        media_type = None
        mime_type = None

        if has_media:
            if hasattr(message.media, "photo"):
                media_type = "photo"
            elif hasattr(message.media, "document"):
                media_type = "document"
                doc = message.media.document
                if hasattr(doc, "mime_type"):
                    mime_type = doc.mime_type
                    if mime_type and mime_type.startswith("video/"):
                        media_type = "video"
                    elif mime_type and mime_type.startswith("audio/"):
                        media_type = "audio"

        urls = []
        text = getattr(message, "message", "") or getattr(message, "text", "") or ""
        entities = getattr(message, "entities", None)
        if entities:
            for entity in entities:
                if hasattr(entity, "url"):
                    urls.append(entity.url)

        import re
        url_pattern = re.compile(r'https?://[^\s]+')
        text_urls = url_pattern.findall(text)
        urls.extend(text_urls)
        urls = list(set(urls))

        return {
            "id": message.id,
            "chat_id": message.chat_id if hasattr(message, "chat_id") else 0,
            "topic_id": topic_id,
            "date": message.date.isoformat() if hasattr(message, "date") else datetime.now().isoformat(),
            "message": text,
            "raw_text": getattr(message, "raw_text", None),
            "out": getattr(message, "out", False),
            "from_id": sender_id,
            "sender_name": sender_name,
            "fwd_from": self._extract_forwarded_from(message),
            "reply_to": str(message.reply_to) if hasattr(message, "reply_to") and message.reply_to else None,
            "edit_date": message.edit_date.isoformat() if hasattr(message, "edit_date") and message.edit_date else None,
            "media": {
                "has_media": has_media,
                "media_type": media_type,
                "mime_type": mime_type,
            } if has_media else None,
            "urls": urls,
            "is_edit": False,
        }

    def _extract_forwarded_from(self, message: Any) -> dict | None:
        """Extract forwarded message info."""
        if not hasattr(message, "fwd_from") or not message.fwd_from:
            return None

        fwd = message.fwd_from
        if fwd is None:
            return None

        result = {}
        if hasattr(fwd, "from_id") and fwd.from_id:
            result["from_id"] = fwd.from_id
        if hasattr(fwd, "from_name") and fwd.from_name:
            result["from_name"] = fwd.from_name
        if hasattr(fwd, "date") and fwd.date:
            result["date"] = fwd.date.isoformat()
        return result if result else None

    async def _store_event(self, chat_id: int, topic_id: int | None, message_id: int, payload: dict) -> None:
        """Store event in database."""
        if not self._db:
            logger.warning("store_event_no_db")
            return

        try:
            await self._db.execute(
                """INSERT OR IGNORE INTO raw_events (chat_id, topic_id, message_id, raw_json, processed_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                (chat_id, topic_id or 0, message_id, str(payload)),
            )
        except Exception as e:
            logger.warning("store_event_error", error=str(e))

    async def _update_event(self, chat_id: int, topic_id: int | None, message_id: int, payload: dict) -> None:
        """Update existing event."""
        if not self._db:
            return

        try:
            conn = await self._db.get_connection()
            async with conn:
                await conn.execute(
                    """UPDATE raw_events SET raw_json = ?, processed_at = CURRENT_TIMESTAMP WHERE chat_id = ? AND message_id = ?""",
                    (str(payload), chat_id, message_id),
                )
                await conn.commit()
        except Exception as e:
            logger.warning("update_event_error", error=str(e))

    async def _queue_processing(self, chat_id: int, message_id: int, topic_id: int | None) -> None:
        """Queue message for async processing."""
        if not self._db:
            return

        try:
            import json

            await self._db.execute(
                """INSERT INTO processing_jobs (job_type, event_id, status, payload, priority) VALUES (?, ?, ?, ?, ?)""",
                (
                    "normalize",
                    None,
                    "pending",
                    json.dumps({"chat_id": chat_id, "message_id": message_id, "topic_id": topic_id}),
                    1 if topic_id else 0,
                ),
            )
        except Exception as e:
            logger.warning("queue_processing_error", error=str(e))

    async def run(self) -> None:
        """Run the ingestion service."""
        await self.initialize()
        self._running = True
        logger.info("ingestion_service_running")

        try:
            if self._client:
                # Start update loop in background
                update_task = asyncio.create_task(self._client.run_until_disconnected())
                
                # Also poll for messages since event handlers aren't working
                while self._running:
                    await self._poll_once()
                    await asyncio.sleep(3)
                
                update_task.cancel()
                self._client.disconnect()
        except asyncio.CancelledError:
            logger.info("service_cancelled")
        except FloodWaitError as e:
            logger.info("flood_wait", seconds=e.seconds)
            await asyncio.sleep(e.seconds)
        except (NetworkMigrateError, PhoneMigrateError) as e:
            logger.error("migration_error", error=str(e))
            await asyncio.sleep(5)
        except Exception as e:
            logger.error("ingestion_error", error=str(e))
        finally:
            self._running = False

    async def _poll_once(self) -> None:
        """Poll for new messages once."""
        if not self._client or not self.settings.telegram:
            return

        config = self.settings.telegram
        try:
            count = 0
            async for message in self._client.iter_messages(config.chat_id, limit=10, min_id=self._last_message_id):
                if message is None:
                    continue
                if message.id <= self._last_message_id:
                    continue

                try:
                    self._last_message_id = message.id
                    chat_id = message.chat_id if hasattr(message, "chat_id") else 0
                    topic_id = self._extract_topic_id(None, message)
                    payload = await self._extract_payload(message, topic_id)

                    await self._raw_storage.store(chat_id, message.id, payload, message.date)
                    await self._store_event(chat_id, topic_id, message.id, payload)
                    await self._queue_processing(chat_id, message.id, topic_id)

                    logger.info("polled_message", message_id=message.id, topic_id=topic_id)
                    count += 1
                except Exception as e:
                    logger.error("message_processing_error", error=str(e), message_id=getattr(message, 'id', None))
            if count == 0:
                logger.debug("poll_no_messages", last_id=self._last_message_id)
        except Exception as e:
            logger.warning("poll_error", error=str(e))

    async def stop(self) -> None:
        """Stop the ingestion service."""
        self._running = False
        if self._client:
            await self._client.disconnect()
        logger.info("ingestion_service_stopped")


async def create_ingestion_service(settings: Settings) -> IngestionService:
    """Factory function to create ingestion service."""
    service = IngestionService(settings)
    await service.initialize()
    return service
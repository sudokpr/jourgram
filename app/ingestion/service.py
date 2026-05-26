"""Ingestion service using Telethon."""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, ServerMigrateError, PhoneMigrateError

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

        self._client.add_event_handler(self._handle_new_message, events.NewMessage)
        self._client.add_event_handler(self._handle_message_edit, events.MessageEdited)
        self._client.add_event_handler(self._handle_new_channel_message, events.NewMessage(incoming=True, chats=[]))

        logger.info("ingestion_service_initialized")

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

    async def _handle_new_channel_message(self, event: events.NewMessage) -> None:
        """Handle new channel messages in topics."""
        pass

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
        if hasattr(message, "entities"):
            for entity in message.entities:
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
            "reply_to": getattr(message, "reply_to", None),
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
        result = {}
        if hasattr(fwd, "from_id") and fwd.from_id:
            result["from_id"] = fwd.from_id
        if hasattr(fwd, "from_name") and fwd.from_name:
            result["from_name"] = fwd.from_name
        if hasattr(fwd, "date") and fwd.date:
            result["date"] = fwd.date.isoformat()
        return result

    async def _store_event(self, chat_id: int, topic_id: int | None, message_id: int, payload: dict) -> None:
        """Store event in database."""
        if not self._db:
            return

        async with self._db.get_connection() as conn:
            await conn.execute(
                """INSERT OR IGNORE INTO raw_events (chat_id, topic_id, message_id, raw_json, processed_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                (chat_id, topic_id or 0, message_id, str(payload)),
            )
            await conn.commit()

    async def _update_event(self, chat_id: int, topic_id: int | None, message_id: int, payload: dict) -> None:
        """Update existing event."""
        if not self._db:
            return

        async with self._db.get_connection() as conn:
            await conn.execute(
                """UPDATE raw_events SET raw_json = ?, processed_at = CURRENT_TIMESTAMP WHERE chat_id = ? AND message_id = ?""",
                (str(payload), chat_id, message_id),
            )
            await conn.commit()

    async def _queue_processing(self, chat_id: int, message_id: int, topic_id: int | None) -> None:
        """Queue message for async processing."""
        if not self._db:
            return

        import json

        async with self._db.get_connection() as conn:
            await conn.execute(
                """INSERT INTO processing_jobs (job_type, event_id, status, payload, priority) VALUES (?, ?, ?, ?, ?)""",
                (
                    "normalize",
                    None,
                    "pending",
                    json.dumps({"chat_id": chat_id, "message_id": message_id, "topic_id": topic_id}),
                    1 if topic_id else 0,
                ),
            )
            await conn.commit()

    async def run(self) -> None:
        """Run the ingestion service."""
        await self.initialize()
        self._running = True
        logger.info("ingestion_service_running")

        try:
            if self._client:
                await self._client.run_until_disconnected()
        except FloodWaitError as e:
            logger.info("flood_wait", seconds=e.seconds)
            await asyncio.sleep(e.seconds)
        except (ServerMigrateError, PhoneMigrateError) as e:
            logger.error("migration_error", error=str(e))
            await asyncio.sleep(5)
        except Exception as e:
            logger.error("ingestion_error", error=str(e))
        finally:
            self._running = False

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
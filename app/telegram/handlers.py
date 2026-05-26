"""Telegram event handlers."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

import structlog
from telethon import events

from app.models import TelegramMessage

logger = structlog.get_logger(__name__)


class EventHandler:
    """Handles Telegram events and routes them for processing."""

    def __init__(self, raw_json_storage: Any, db: Any, queue: Any) -> None:
        self.raw_json_storage = raw_json_storage
        self.db = db
        self.queue = queue
        self._handlers: list[Callable] = []

    def register_handler(self, handler: Callable) -> None:
        """Register an event handler."""
        self._handlers.append(handler)

    async def handle_new_message(self, event: events.NewMessage) -> None:
        """Handle new message event."""
        try:
            await self._process_message(event.message, event)

            for handler in self._handlers:
                try:
                    await handler(event)
                except Exception as e:
                    logger.error("handler_error", handler=handler.__name__, error=str(e))

        except Exception as e:
            logger.error("message_handle_error", error=str(e), message_id=event.message.id)

    async def handle_message_edit(self, event: events.MessageEdited) -> None:
        """Handle message edit event."""
        try:
            await self._process_message(event.message, event, is_edit=True)
        except Exception as e:
            logger.error("edit_handle_error", error=str(e), message_id=event.message.id)

    async def _process_message(self, message: Any, event: Any, is_edit: bool = False) -> None:
        """Process a message and store it."""
        chat_id = message.chat_id if hasattr(message, "chat_id") else message.peer_id.channel_id if hasattr(message.peer_id, "channel_id") else message.peer_id.user_id if hasattr(message.peer_id, "user_id") else 0

        thread_id = None
        if hasattr(event, "reply_to_msg_id") and event.reply_to_msg_id:
            thread_id = event.reply_to_msg_id
        if hasattr(message, "reply_to") and message.reply_to:
            thread_id = getattr(message.reply_to.reply_to_top_id, None, None) or getattr(message.reply_to.reply_to_msg_id, None, None)

        payload = self._extract_payload(message, event, chat_id, thread_id, is_edit)

        raw_path = await self.raw_json_storage.store(chat_id, message.id, payload, message.date)

        await self._store_event(chat_id, thread_id or 0, message.id, payload, is_edit)

        await self._queue_for_processing(chat_id, message.id, is_edit)

        logger.debug(
            "message_processed",
            chat_id=chat_id,
            message_id=message.id,
            thread_id=thread_id,
            is_edit=is_edit,
        )

    def _extract_payload(self, message: Any, event: Any, chat_id: int, thread_id: int | None, is_edit: bool) -> dict[str, Any]:
        """Extract message data into a serializable dict."""
        sender_id = None
        sender_name = None
        if hasattr(message, "from_id") and message.from_id:
            if hasattr(message.from_id, "user_id"):
                sender_id = message.from_id.user_id
            elif hasattr(message.from_id, "channel_id"):
                sender_id = message.from_id.channel_id

        if hasattr(message, "sender") and message.sender:
            sender_name = getattr(message.sender, "first_name", None) or getattr(message.sender, "title", None) or str(sender_id)

        media_type = None
        media_url = None
        has_media = False
        if hasattr(message, "media") and message.media:
            has_media = True
            media_type = type(message.media).__name__
            if hasattr(message.media, "photo") and message.media.photo:
                media_type = "photo"
            elif hasattr(message.media, "document") and message.media.document:
                media_type = "document"
                if hasattr(message.media.document, "mime_type"):
                    if message.media.document.mime_type.startswith("video/"):
                        media_type = "video"
                    elif message.media.document.mime_type.startswith("audio/"):
                        media_type = "audio"
                    elif message.media.document.mime_type == "application/pdf":
                        media_type = "pdf"

        urls = []
        if hasattr(message, "entities") and message.entities:
            text = getattr(message, "message", "") or ""
            for entity in message.entities:
                if hasattr(entity, "url"):
                    urls.append(entity.url)
                elif hasattr(entity, "type") and entity.type == "url":
                    pass

        return {
            "id": message.id,
            "chat_id": chat_id,
            "thread_id": thread_id,
            "date": message.date.isoformat() if hasattr(message, "date") and message.date else datetime.now().isoformat(),
            "message": getattr(message, "message", None),
            "raw_text": getattr(message, "raw_text", None),
            "out": getattr(message, "out", False),
            "mentioned": getattr(message, "mentioned", False),
            "silent": getattr(message, "silent", False),
            "post": getattr(message, "post", False),
            "from_id": sender_id,
            "sender_name": sender_name,
            "fwd_from": getattr(message, "fwd_from", None),
            "reply_to": getattr(message, "reply_to", None),
            "edit_date": message.edit_date.isoformat() if hasattr(message, "edit_date") and message.edit_date else None,
            "media": {
                "has_media": has_media,
                "media_type": media_type,
                "mime_type": getattr(message.media, "mime_type", None) if has_media and hasattr(message, "media") else None,
            } if has_media else None,
            "urls": urls,
            "is_edit": is_edit,
        }

    async def _store_event(self, chat_id: int, topic_id: int, message_id: int, payload: dict, is_edit: bool) -> None:
        """Store event in database."""
        from app.storage.database import Database

        db = Database(self.db.settings if hasattr(self.db, "settings") else self.db)

        async with db.get_connection() as conn:
            if is_edit:
                await conn.execute(
                    """UPDATE raw_events SET processed_at = CURRENT_TIMESTAMP WHERE chat_id = ? AND message_id = ?""",
                    (chat_id, message_id),
                )
            else:
                await conn.execute(
                    """INSERT OR IGNORE INTO raw_events (chat_id, topic_id, message_id, raw_json) VALUES (?, ?, ?, ?)""",
                    (chat_id, topic_id, message_id, str(payload)),
                )
            await conn.commit()

    async def _queue_for_processing(self, chat_id: int, message_id: int, is_edit: bool) -> None:
        """Queue message for async processing."""
        if self.queue is None:
            return

        job_type = "normalize" if not is_edit else "normalize_edit"
        job_payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "is_edit": is_edit,
        }

        if hasattr(self.queue, "enqueue"):
            await self.queue.enqueue(job_type, payload=job_payload)
        elif hasattr(self.queue, "put"):
            self.queue.put_nowait({"type": job_type, "payload": job_payload})
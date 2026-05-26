"""Query handler for API-like operations."""

from __future__ import annotations

from datetime import datetime, timedelta

import structlog

from app.config.settings import Settings
from app.search.engine import SearchEngine
from app.storage import Database

logger = structlog.get_logger(__name__)


class QueryHandler:
    """Handler for various query operations."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._db: Database | None = None
        self._search: SearchEngine | None = None

    async def initialize(self) -> None:
        """Initialize the handler."""
        self._db = Database(self.settings)
        await self._db.initialize()
        self._search = SearchEngine(self.settings)
        await self._search.initialize()

    async def get_today_summary(self) -> dict:
        """Get today's summary."""
        await self.initialize()

        today = datetime.now().strftime("%Y-%m-%d")
        async with self._db.get_connection() as conn:
            cursor = await conn.execute(
                """SELECT content, topics_json, metrics_json FROM daily_summaries WHERE date = ?""",
                (today,),
            )
            row = await cursor.fetchone()

        if row:
            return {
                "date": today,
                "content": row[0],
                "topics": row[1],
                "metrics": row[2],
            }

        messages = await self._get_today_messages()
        return {
            "date": today,
            "message_count": len(messages),
            "messages": messages[:10],
        }

    async def _get_today_messages(self) -> list[dict]:
        """Get today's messages."""
        start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

        async with self._db.get_connection() as conn:
            cursor = await conn.execute(
                """SELECT message_id, text, sender_name, timestamp, topic_id FROM normalized_messages 
                WHERE timestamp >= ? AND timestamp < ? ORDER BY timestamp DESC LIMIT 20""",
                (start.isoformat(), end.isoformat()),
            )
            rows = await cursor.fetchall()

        return [
            {
                "message_id": row[0],
                "text": row[1][:100] if row[1] else None,
                "sender": row[2],
                "time": row[3],
                "topic_id": row[4],
            }
            for row in rows
        ]

    async def get_stats(self) -> dict:
        """Get overall statistics."""
        await self.initialize()

        stats = {}

        async with self._db.get_connection() as conn:
            cursor = await conn.execute("SELECT COUNT(*) FROM normalized_messages")
            stats["total_messages"] = (await cursor.fetchone())[0]

            cursor = await conn.execute("SELECT COUNT(*) FROM media")
            stats["total_media"] = (await cursor.fetchone())[0]

            cursor = await conn.execute("SELECT COUNT(*) FROM links_knowledge_base WHERE fetch_status = 'completed'")
            stats["total_links"] = (await cursor.fetchone())[0]

            cursor = await conn.execute("SELECT COUNT(*) FROM daily_summaries")
            stats["total_summaries"] = (await cursor.fetchone())[0]

            cursor = await conn.execute(
                """SELECT COUNT(DISTINCT DATE(timestamp)) FROM normalized_messages"""
            )
            stats["active_days"] = (await cursor.fetchone())[0]

        return stats

    async def get_topic_summary(self, topic_id: int) -> dict:
        """Get summary for a specific topic."""
        await self.initialize()

        async with self._db.get_connection() as conn:
            cursor = await conn.execute(
                """SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM normalized_messages WHERE topic_id = ?""",
                (topic_id,),
            )
            row = await cursor.fetchone()

        return {
            "topic_id": topic_id,
            "message_count": row[0] if row else 0,
            "first_message": row[1] if row else None,
            "last_message": row[2] if row else None,
        }
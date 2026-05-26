"""Search engine using SQLite FTS5."""

from __future__ import annotations

import json
from datetime import datetime

import structlog

from app.config.settings import Settings
from app.storage import Database

logger = structlog.get_logger(__name__)


class SearchEngine:
    """Search engine for messages using FTS5."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._db: Database | None = None

    async def initialize(self) -> None:
        """Initialize the search engine."""
        self._db = Database(self.settings)
        await self._db.initialize()

    async def search(self, query: str, limit: int = 10) -> list[dict]:
        """Search messages using FTS5."""
        if not self._db:
            await self.initialize()

        results = []
        async with self._db.get_connection() as conn:
            cursor = await conn.execute(
                """SELECT 
                    nm.id, nm.message_id, nm.chat_id, nm.topic_id, nm.text, 
                    nm.sender_name, nm.timestamp, nm.url_count,
                    highlight(search_index, 4, '<mark>', '</mark>') as highlighted_text
                FROM search_index si
                JOIN normalized_messages nm ON nm.id = si.rowid
                WHERE search_index MATCH ?
                ORDER BY rank
                LIMIT ?""",
                (query, limit),
            )
            rows = await cursor.fetchall()

        for row in rows:
            results.append({
                "id": row[0],
                "message_id": row[1],
                "chat_id": row[2],
                "topic_id": row[3],
                "text": row[4],
                "sender_name": row[5],
                "timestamp": row[6],
                "url_count": row[7],
                "highlighted_text": row[8],
            })

        return results

    async def search_by_date_range(self, start_date: datetime, end_date: datetime, query: str, limit: int = 50) -> list[dict]:
        """Search messages within date range."""
        if not self._db:
            await self.initialize()

        results = []
        async with self._db.get_connection() as conn:
            cursor = await conn.execute(
                """SELECT 
                    nm.id, nm.message_id, nm.chat_id, nm.topic_id, nm.text, 
                    nm.sender_name, nm.timestamp, nm.url_count
                FROM normalized_messages nm
                JOIN search_index si ON nm.id = si.rowid
                WHERE search_index MATCH ? AND nm.timestamp >= ? AND nm.timestamp <= ?
                ORDER BY nm.timestamp DESC
                LIMIT ?""",
                (query, start_date.isoformat(), end_date.isoformat(), limit),
            )
            rows = await cursor.fetchall()

        for row in rows:
            results.append({
                "id": row[0],
                "message_id": row[1],
                "chat_id": row[2],
                "topic_id": row[3],
                "text": row[4],
                "sender_name": row[5],
                "timestamp": row[6],
                "url_count": row[7],
            })

        return results

    async def search_by_topic(self, topic_id: int, query: str, limit: int = 20) -> list[dict]:
        """Search messages within a specific topic."""
        if not self._db:
            await self.initialize()

        results = []
        async with self._db.get_connection() as conn:
            cursor = await conn.execute(
                """SELECT 
                    nm.id, nm.message_id, nm.chat_id, nm.topic_id, nm.text, 
                    nm.sender_name, nm.timestamp, nm.url_count
                FROM normalized_messages nm
                JOIN search_index si ON nm.id = si.rowid
                WHERE search_index MATCH ? AND nm.topic_id = ?
                ORDER BY nm.timestamp DESC
                LIMIT ?""",
                (query, topic_id, limit),
            )
            rows = await cursor.fetchall()

        for row in rows:
            results.append({
                "id": row[0],
                "message_id": row[1],
                "chat_id": row[2],
                "topic_id": row[3],
                "text": row[4],
                "sender_name": row[5],
                "timestamp": row[6],
                "url_count": row[7],
            })

        return results

    async def get_recent(self, limit: int = 20, topic_id: int | None = None) -> list[dict]:
        """Get recent messages."""
        if not self._db:
            await self.initialize()

        query = """SELECT 
            nm.id, nm.message_id, nm.chat_id, nm.topic_id, nm.text, 
            nm.sender_name, nm.timestamp, nm.url_count, nm.has_media, nm.media_type
        FROM normalized_messages nm
        """
        params = []

        if topic_id:
            query += " WHERE nm.topic_id = ?"
            params.append(topic_id)

        query += " ORDER BY nm.timestamp DESC LIMIT ?"
        params.append(limit)

        results = []
        async with self._db.get_connection() as conn:
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()

        for row in rows:
            results.append({
                "id": row[0],
                "message_id": row[1],
                "chat_id": row[2],
                "topic_id": row[3],
                "text": row[4],
                "sender_name": row[5],
                "timestamp": row[6],
                "url_count": row[7],
                "has_media": row[8],
                "media_type": row[9],
            })

        return results


class SearchIndexer:
    """Indexer for rebuilding search index."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._db: Database | None = None

    async def initialize(self) -> None:
        """Initialize the indexer."""
        self._db = Database(self.settings)
        await self._db.initialize()

    async def rebuild(self) -> int:
        """Rebuild the entire search index."""
        if not self._db:
            await self.initialize()

        logger.info("search_index_rebuild_started")

        async with self._db.get_connection() as conn:
            await conn.execute("DELETE FROM search_index")
            await conn.commit()

        indexed = 0
        batch_size = 100
        offset = 0

        while True:
            async with self._db.get_connection() as conn:
                cursor = await conn.execute(
                    """SELECT id, message_id, chat_id, topic_id, text, sender_name 
                    FROM normalized_messages 
                    ORDER BY id 
                    LIMIT ? OFFSET ?""",
                    (batch_size, offset),
                )
                rows = await cursor.fetchall()

            if not rows:
                break

            for row in rows:
                await self._index_row(row)
                indexed += 1

            offset += batch_size
            logger.debug("indexing_progress", indexed=indexed)

        logger.info("search_index_rebuild_completed", total=indexed)
        return indexed

    async def _index_row(self, row: tuple) -> None:
        """Index a single row."""
        if not self._db:
            return

        id_, message_id, chat_id, topic_id, text, sender_name = row

        async with self._db.get_connection() as conn:
            await conn.execute(
                """INSERT INTO search_index(rowid, message_id, chat_id, topic_id, text, sender_name) VALUES (?, ?, ?, ?, ?, ?)""",
                (id_, message_id, chat_id, topic_id or 0, text or "", sender_name or ""),
            )
            await conn.commit()
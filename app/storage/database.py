"""Database initialization and schema management."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import aiosqlite

from app.config.settings import Settings


SCHEMA_SQL = """
-- Chats table: stores telegram chat/group metadata
CREATE TABLE IF NOT EXISTS chats (
    chat_id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    type TEXT NOT NULL,
    username TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Topics table: telegram topic metadata within chats
CREATE TABLE IF NOT EXISTS topics (
    topic_id INTEGER PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    thread_id INTEGER NOT NULL,
    title TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES chats(chat_id),
    UNIQUE(chat_id, thread_id)
);

-- Raw events table: stores raw telegram message JSON
CREATE TABLE IF NOT EXISTS raw_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    topic_id INTEGER,
    message_id INTEGER NOT NULL,
    raw_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP,
    UNIQUE(chat_id, message_id)
);

-- Normalized messages table
CREATE TABLE IF NOT EXISTS normalized_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL UNIQUE,
    chat_id INTEGER NOT NULL,
    topic_id INTEGER,
    message_id INTEGER NOT NULL,
    text TEXT,
    raw_text TEXT,
    sender_id INTEGER,
    sender_name TEXT,
    timestamp TIMESTAMP NOT NULL,
    edited_at TIMESTAMP,
    is_forwarded BOOLEAN DEFAULT 0,
    forwarded_from_chat_id INTEGER,
    forwarded_from_message_id INTEGER,
    reply_to_message_id INTEGER,
    has_media BOOLEAN DEFAULT 0,
    media_type TEXT,
    has_urls BOOLEAN DEFAULT 0,
    url_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (event_id) REFERENCES raw_events(event_id)
);

-- Media table: stores media file metadata
CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL UNIQUE,
    normalized_message_id INTEGER NOT NULL,
    file_type TEXT NOT NULL,
    file_name TEXT,
    file_size INTEGER,
    mime_type TEXT,
    width INTEGER,
    height INTEGER,
    duration INTEGER,
    local_path TEXT,
    remote_url TEXT,
    thumbnail_path TEXT,
    caption TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (event_id) REFERENCES raw_events(event_id),
    FOREIGN KEY (normalized_message_id) REFERENCES normalized_messages(id)
);

-- Links knowledge base
CREATE TABLE IF NOT EXISTS links_knowledge_base (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    canonical_url TEXT,
    title TEXT,
    source TEXT,
    domain TEXT,
    extracted_text TEXT,
    summary TEXT,
    tags TEXT,
    fetch_status TEXT DEFAULT 'pending',
    fetch_error TEXT,
    fetched_at TIMESTAMP,
    last_checked_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Daily summaries
CREATE TABLE IF NOT EXISTS daily_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL UNIQUE,
    content TEXT NOT NULL,
    topics_json TEXT,
    metrics_json TEXT,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Weekly summaries
CREATE TABLE IF NOT EXISTS weekly_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    content TEXT NOT NULL,
    daily_summaries_json TEXT,
    metrics_json TEXT,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Search index (FTS5)
CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(
    message_id,
    chat_id,
    topic_id,
    text,
    sender_name,
    content='normalized_messages',
    content_rowid='id'
);

-- Processing jobs for async workers
CREATE TABLE IF NOT EXISTS processing_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type TEXT NOT NULL,
    event_id INTEGER,
    status TEXT DEFAULT 'pending',
    priority INTEGER DEFAULT 0,
    payload TEXT,
    result TEXT,
    error TEXT,
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- Embeddings table for future semantic search
CREATE TABLE IF NOT EXISTS embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,
    source_id INTEGER NOT NULL,
    model TEXT NOT NULL,
    embedding_vector BLOB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_type, source_id, model)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_raw_events_chat ON raw_events(chat_id);
CREATE INDEX IF NOT EXISTS idx_raw_events_topic ON raw_events(topic_id);
CREATE INDEX IF NOT EXISTS idx_raw_events_created ON raw_events(created_at);
CREATE INDEX IF NOT EXISTS idx_normalized_timestamp ON normalized_messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_normalized_chat ON normalized_messages(chat_id);
CREATE INDEX IF NOT EXISTS idx_normalized_topic ON normalized_messages(topic_id);
CREATE INDEX IF NOT EXISTS idx_media_event ON media(event_id);
CREATE INDEX IF NOT EXISTS idx_links_status ON links_knowledge_base(fetch_status);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON processing_jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_type ON processing_jobs(job_type);

-- Triggers to keep search_index in sync
CREATE TRIGGER IF NOT EXISTS normalized_messages_ai AFTER INSERT ON normalized_messages BEGIN
    INSERT INTO search_index(rowid, message_id, chat_id, topic_id, text, sender_name)
    VALUES (new.id, new.message_id, new.chat_id, new.topic_id, new.text, new.sender_name);
END;

CREATE TRIGGER IF NOT EXISTS normalized_messages_ad AFTER DELETE ON normalized_messages BEGIN
    INSERT INTO search_index(search_index, rowid, message_id, chat_id, topic_id, text, sender_name)
    VALUES ('delete', old.id, old.message_id, old.chat_id, old.topic_id, old.text, old.sender_name);
END;

CREATE TRIGGER IF NOT EXISTS normalized_messages_au AFTER UPDATE ON normalized_messages BEGIN
    INSERT INTO search_index(search_index, rowid, message_id, chat_id, topic_id, text, sender_name)
    VALUES ('delete', old.id, old.message_id, old.chat_id, old.topic_id, old.text, old.sender_name);
    INSERT INTO search_index(rowid, message_id, chat_id, topic_id, text, sender_name)
    VALUES (new.id, new.message_id, new.chat_id, new.topic_id, new.text, new.sender_name);
END;
"""


class Database:
    """Database manager for Life Data Lake."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db_path = settings.storage.data_dir / "life_data_lake.db"

    async def initialize(self) -> None:
        """Initialize database with schema."""
        self.settings.storage.data_dir.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = sqlite3.Row
            await db.executescript(SCHEMA_SQL)
            await db.commit()

    async def get_connection(self) -> aiosqlite.Connection:
        """Get a database connection with timeout handling."""
        conn = aiosqlite.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        await conn.execute("PRAGMA journal_mode = WAL")
        await conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    async def execute(self, query: str, params: tuple | None = None) -> sqlite3.Cursor:
        """Execute a query."""
        async with self.get_connection() as db:
            return await db.execute(query, params or ())

    async def execute_many(self, query: str, params_list: list[tuple]) -> None:
        """Execute a query with multiple parameter sets."""
        async with self.get_connection() as db:
            await db.executemany(query, params_list)
            await db.commit()

    async def fetch_one(self, query: str, params: tuple | None = None) -> sqlite3.Row | None:
        """Fetch one result."""
        async with self.get_connection() as db:
            cursor = await db.execute(query, params or ())
            return await cursor.fetchone()

    async def fetch_all(self, query: str, params: tuple | None = None) -> list[sqlite3.Row]:
        """Fetch all results."""
        async with self.get_connection() as db:
            cursor = await db.execute(query, params or ())
            return await cursor.fetchall()

    async def close(self) -> None:
        """Close database connections."""
        pass


async def init_database(settings: Settings) -> Database:
    """Initialize the database."""
    db = Database(settings)
    await db.initialize()
    return db
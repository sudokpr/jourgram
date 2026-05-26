"""Data exporter for JSON and CSV formats."""

from __future__ import annotations

import asyncio
import csv
import json
from datetime import datetime
from pathlib import Path

import aiosqlite

from app.config.settings import Settings

CHAT_QUERY = """
SELECT 
    nm.id, nm.message_id, nm.chat_id, nm.topic_id, nm.text, nm.raw_text,
    nm.sender_id, nm.sender_name, nm.timestamp, nm.edited_at,
    nm.is_forwarded, nm.forwarded_from_chat_id, nm.forwarded_from_message_id,
    nm.reply_to_message_id, nm.has_media, nm.media_type,
    nm.has_urls, nm.url_count,
    m.file_name, m.mime_type, m.local_path
FROM normalized_messages nm
LEFT JOIN media m ON m.normalized_message_id = nm.id
WHERE nm.timestamp >= ? AND nm.timestamp <= ?
ORDER BY nm.timestamp
"""


class Exporter:
    """Export data to various formats."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db_path = settings.storage.data_dir / "life_data_lake.db"

    async def export(
        self,
        format: str,
        output_dir: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Path:
        """Export data to specified format."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        start = datetime.fromisoformat(start_date) if start_date else datetime(2020, 1, 1)
        end = datetime.fromisoformat(end_date) if end_date else datetime.now()

        if format == "json":
            return await self._export_json(output_dir, start, end)
        elif format == "csv":
            return await self._export_csv(output_dir, start, end)
        else:
            raise ValueError(f"Unsupported format: {format}")

    async def _export_json(self, output_dir: Path, start: datetime, end: datetime) -> Path:
        """Export to JSON format."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
            cursor = await db.execute(CHAT_QUERY, (start.isoformat(), end.isoformat()))
            rows = await cursor.fetchall()

        output_file = output_dir / f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2, default=str)

        return output_file

    async def _export_csv(self, output_dir: Path, start: datetime, end: datetime) -> Path:
        """Export to CSV format."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
            cursor = await db.execute(CHAT_QUERY, (start.isoformat(), end.isoformat()))
            rows = await cursor.fetchall()

        output_file = output_dir / f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        if rows:
            with open(output_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)

        return output_file
"""Raw JSON storage on filesystem."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


class RawJsonStorage:
    """Stores raw Telegram JSON payloads on filesystem."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_date_path(self, date: datetime | None = None) -> Path:
        """Get path for date directory."""
        if date is None:
            date = datetime.now()
        return self.base_dir / date.strftime("%Y/%m/%d")

    async def store(
        self,
        chat_id: int,
        message_id: int,
        payload: dict,
        date: datetime | None = None,
    ) -> Path:
        """Store raw JSON payload."""
        date_path = self._get_date_path(date)
        date_path.mkdir(parents=True, exist_ok=True)

        filename = f"{chat_id}_{message_id}.json"
        file_path = date_path / filename

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

        logger.debug("stored_raw_json", path=str(file_path))
        return file_path

    async def load(self, chat_id: int, message_id: int, date: datetime | None = None) -> dict | None:
        """Load raw JSON payload."""
        date_path = self._get_date_path(date)
        filename = f"{chat_id}_{message_id}.json"
        file_path = date_path / filename

        if not file_path.exists():
            return None

        with open(file_path, encoding="utf-8") as f:
            return json.load(f)

    async def list_raw_files(self, start_date: datetime | None = None, end_date: datetime | None = None) -> list[Path]:
        """List all raw JSON files within date range."""
        if start_date is None:
            start_date = datetime(2020, 1, 1)
        if end_date is None:
            end_date = datetime.now()

        files = []
        current = start_date
        while current <= end_date:
            date_path = self._get_date_path(current)
            if date_path.exists():
                files.extend(date_path.glob("*.json"))
            current = current.replace(day=current.day + 1) if current.day < 28 else current.replace(month=current.month + 1, day=1)
            if current.month > 12:
                current = current.replace(year=current.year + 1, month=1)

        return sorted(files)
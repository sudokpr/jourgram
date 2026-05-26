"""Media storage manager."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import BinaryIO

import aiohttp
import structlog

logger = structlog.get_logger(__name__)


class MediaStorage:
    """Manages media file storage."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_date_path(self, date: datetime | None = None) -> Path:
        """Get path for date directory."""
        if date is None:
            date = datetime.now()
        return self.base_dir / date.strftime("%Y/%m/%d")

    async def store_file(
        self,
        chat_id: int,
        message_id: int,
        file_data: BinaryIO,
        filename: str,
        mime_type: str | None = None,
        date: datetime | None = None,
    ) -> Path:
        """Store a media file."""
        date_path = self._get_date_path(date)
        date_path.mkdir(parents=True, exist_ok=True)

        ext = Path(filename).suffix or self._get_ext_from_mime(mime_type)
        safe_name = f"{chat_id}_{message_id}{ext}"
        file_path = date_path / safe_name

        with open(file_path, "wb") as f:
            content = file_data.read()
            if isinstance(file_data, bytes):
                content = file_data
            f.write(content)

        logger.debug("stored_media", path=str(file_path))
        return file_path

    async def download_and_store(
        self,
        url: str,
        chat_id: int,
        message_id: int,
        date: datetime | None = None,
    ) -> Path | None:
        """Download media from URL and store locally."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status != 200:
                        logger.warning("media_download_failed", url=url, status=resp.status)
                        return None

                    content = await resp.read()
                    content_type = resp.headers.get("Content-Type", "")

                    date_path = self._get_date_path(date)
                    date_path.mkdir(parents=True, exist_ok=True)

                    ext = self._get_ext_from_mime(content_type)
                    safe_name = f"{chat_id}_{message_id}{ext}"
                    file_path = date_path / safe_name

                    with open(file_path, "wb") as f:
                        f.write(content)

                    logger.debug("downloaded_media", path=str(file_path))
                    return file_path

        except Exception as e:
            logger.error("media_download_error", url=url, error=str(e))
            return None

    def _get_ext_from_mime(self, mime_type: str | None) -> str:
        """Get file extension from MIME type."""
        if not mime_type:
            return ""
        ext_map = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "video/mp4": ".mp4",
            "video/quicktime": ".mov",
            "audio/ogg": ".ogg",
            "application/pdf": ".pdf",
            "application/zip": ".zip",
        }
        return ext_map.get(mime_type, "")

    def get_local_path(self, chat_id: int, message_id: int, date: datetime | None = None) -> Path:
        """Get expected local path for a media file."""
        date_path = self._get_date_path(date)
        return date_path / f"{chat_id}_{message_id}"
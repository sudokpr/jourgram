"""Link knowledge base processor."""

from __future__ import annotations

import json
import re
from datetime import datetime
from urllib.parse import urlparse

import aiohttp
import structlog
import trafilatura

from app.config.settings import Settings
from app.storage import Database

logger = structlog.get_logger(__name__)


class LinkProcessor:
    """Processor for extracting and storing link content."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._db: Database | None = None

    async def initialize(self) -> None:
        """Initialize the processor."""
        self._db = Database(self.settings)
        await self._db.initialize()

    async def process_pending(self) -> int:
        """Process pending link extraction jobs."""
        if not self._db:
            await self.initialize()

        processed = 0
        async with self._db.get_connection() as conn:
            cursor = await conn.execute(
                """SELECT id, payload FROM processing_jobs WHERE status = 'pending' AND job_type = 'fetch_link' ORDER BY created_at ASC LIMIT ?""",
                (self.settings.processing.batch_size,),
            )
            jobs = await cursor.fetchall()

        for job in jobs:
            try:
                await self._process_job(job)
                processed += 1
            except Exception as e:
                logger.error("link_processing_job_failed", job_id=job[0], error=str(e))
                await self._mark_job_failed(job[0], str(e))

        return processed

    async def _process_job(self, job: tuple) -> None:
        """Process a single link extraction job."""
        job_id, payload_str = job
        payload = json.loads(payload_str)

        chat_id = payload["chat_id"]
        message_id = payload["message_id"]

        urls = await self._get_urls_from_message(chat_id, message_id)
        if not urls:
            await self._mark_job_completed(job_id)
            return

        for url in urls:
            await self._process_url(url)

        await self._mark_job_completed(job_id)

    async def _get_urls_from_message(self, chat_id: int, message_id: int) -> list[str]:
        """Get URLs from normalized message."""
        if not self._db:
            return []

        async with self._db.get_connection() as conn:
            cursor = await conn.execute(
                """SELECT text FROM normalized_messages WHERE chat_id = ? AND message_id = ?""",
                (chat_id, message_id),
            )
            row = await cursor.fetchone()
            if not row or not row[0]:
                return []

            text = row[0]
            url_pattern = re.compile(r'https?://[^\s]+')
            urls = url_pattern.findall(text)
            return urls

    async def _process_url(self, url: str) -> None:
        """Process a single URL - extract content and store."""
        if not self._db:
            return

        domain = urlparse(url).netloc

        async with self._db.get_connection() as conn:
            await conn.execute(
                """INSERT OR IGNORE INTO links_knowledge_base (url, domain, fetch_status) VALUES (?, ?, 'processing')""",
                (url, domain),
            )
            await conn.commit()

        try:
            downloaded = await self._fetch_url_content(url)

            if downloaded:
                extracted = await self._extract_content(downloaded)

                async with self._db.get_connection() as conn:
                    await conn.execute(
                        """UPDATE links_knowledge_base SET 
                        canonical_url = ?,
                        title = ?,
                        source = ?,
                        domain = ?,
                        extracted_text = ?,
                        summary = ?,
                        fetch_status = 'completed',
                        fetched_at = CURRENT_TIMESTAMP
                        WHERE url = ?""",
                        (
                            extracted.get("canonical_url", url),
                            extracted.get("title"),
                            extracted.get("source"),
                            domain,
                            extracted.get("text"),
                            extracted.get("summary"),
                            url,
                        ),
                    )
                    await conn.commit()

                logger.info("link_processed", url=url, title=extracted.get("title"))

        except Exception as e:
            logger.error("link_fetch_failed", url=url, error=str(e))

            async with self._db.get_connection() as conn:
                await conn.execute(
                    """UPDATE links_knowledge_base SET fetch_status = 'failed', fetch_error = ? WHERE url = ?""",
                    (str(e), url),
                )
                await conn.commit()

    async def _fetch_url_content(self, url: str) -> bytes | None:
        """Fetch URL content using trafilatura."""
        timeout = aiohttp.ClientTimeout(total=self.settings.processing.link_fetch_timeout)

        try:
            downloaded = await trafilatura.fetch_url(url, timeout=timeout)
            return downloaded
        except Exception as e:
            logger.warning("trafilatura_fetch_failed", url=url, error=str(e))

            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                        if resp.status == 200:
                            return await resp.read()
            except Exception as e2:
                logger.warning("aiohttp_fetch_failed", url=url, error=str(e2))

        return None

    async def _extract_content(self, content: bytes | str) -> dict:
        """Extract content from downloaded page."""
        text = content.decode("utf-8", errors="ignore") if isinstance(content, bytes) else content

        try:
            result = trafilatura.extract(text, include_comments=False, include_images=False)

            if result:
                return {
                    "text": result,
                    "title": self._extract_title(text),
                    "source": self._extract_source(text),
                    "canonical_url": self._extract_canonical(text),
                }

        except Exception as e:
            logger.warning("content_extraction_failed", error=str(e))

        return {
            "text": text[:10000] if len(text) > 10000 else text,
            "title": None,
            "source": None,
            "canonical_url": None,
        }

    def _extract_title(self, html: str) -> str | None:
        """Extract title from HTML."""
        title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
        if title_match:
            return title_match.group(1).strip()
        return None

    def _extract_source(self, html: str) -> str | None:
        """Extract source/author from HTML."""
        author_match = re.search(r'<meta[^>]+name=["\']author["\'][^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if author_match:
            return author_match.group(1)
        og_site_match = re.search(r'<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if og_site_match:
            return og_site_match.group(1)
        return None

    def _extract_canonical(self, html: str) -> str | None:
        """Extract canonical URL from HTML."""
        canonical_match = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if canonical_match:
            return canonical_match.group(1)
        return None

    async def _mark_job_completed(self, job_id: int) -> None:
        """Mark a job as completed."""
        if not self._db:
            return

        async with self._db.get_connection() as conn:
            await conn.execute(
                """UPDATE processing_jobs SET status = 'completed', completed_at = CURRENT_TIMESTAMP WHERE id = ?""",
                (job_id,),
            )
            await conn.commit()

    async def _mark_job_failed(self, job_id: int, error: str) -> None:
        """Mark a job as failed."""
        if not self._db:
            return

        async with self._db.get_connection() as conn:
            await conn.execute(
                """UPDATE processing_jobs SET status = 'failed', error = ?, attempts = attempts + 1 WHERE id = ?""",
                (error, job_id),
            )
            await conn.commit()
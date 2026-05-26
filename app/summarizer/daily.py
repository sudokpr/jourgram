"""Daily summarizer using Gemini."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import structlog

from app.config.settings import Settings
from app.llm import GeminiProvider
from app.storage import Database

logger = structlog.get_logger(__name__)

DAILY_SUMMARY_PROMPT = """You are analyzing a day's worth of personal journal entries and messages. Generate a thoughtful, reflective summary that feels personal and meaningful.

Today's Date: {date}

=== JOURNAL ENTRIES ===
{journal_content}

=== LEARNINGS ===
{learning_content}

=== IDEAS ===
{ideas_content}

=== EXPENSES ===
{expenses_content}

=== LINKS SHARED ===
{links_content}

=== QUICK DUMP ===
{quick_dump_content}

Please provide a summary that:
1. Extracts key themes and patterns from the day
2. Identifies todos or action items mentioned
3. Notes any recurring topics or interests
4. Highlights any significant insights or ideas
5. Summarizes expenses if any were recorded
6. Lists important links shared

Format your response as a JSON object with these fields:
- summary: A reflective, journal-like paragraph summarizing the day
- themes: Array of key themes observed
- todos: Array of todo items found
- learnings: Array of new learnings or insights
- ideas: Array of notable ideas
- expenses: Object with expense summary (if any)
- links: Array of important links mentioned
- health_notes: Any health-related observations
- tomorrow_preview: What seems to be coming up next

Keep the tone warm and reflective, as if writing a personal journal entry.
"""


class DailySummarizer:
    """Generates daily summaries using LLM."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._db: Database | None = None
        self._llm: GeminiProvider | None = None

    async def initialize(self) -> None:
        """Initialize the summarizer."""
        self._db = Database(self.settings)
        await self._db.initialize()

        if self.settings.gemini:
            self._llm = GeminiProvider(
                api_key=self.settings.gemini.api_key,
                model=self.settings.gemini.model_daily,
            )

    async def summarize_today(self, force: bool = False) -> dict:
        """Generate summary for today."""
        today = datetime.now().strftime("%Y-%m-%d")
        return await self.summarize_date(today, force=force)

    async def summarize_date(self, date_str: str, force: bool = False) -> dict:
        """Generate summary for a specific date."""
        await self.initialize()

        existing = await self._get_existing_summary(date_str)
        if existing and not force:
            logger.info("summary_already_exists", date=date_str)
            return existing

        messages = await self._get_messages_for_date(date_str)
        if not messages:
            logger.info("no_messages_for_date", date=date_str)
            return {"date": date_str, "content": "No messages found for this date."}

        grouped = self._group_by_topic(messages)
        prompt = self._build_prompt(date_str, grouped)

        content = await self._generate_summary(prompt)

        summary = await self._store_summary(date_str, content, grouped)

        logger.info("daily_summary_generated", date=date_str)
        return summary

    async def summarize_range(self, start_date: str, end_date: str) -> list[dict]:
        """Generate summaries for a date range."""
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)

        summaries = []
        current = start

        while current <= end:
            date_str = current.strftime("%Y-%m-%d")
            try:
                summary = await self.summarize_date(date_str)
                summaries.append(summary)
            except Exception as e:
                logger.error("summary_failed", date=date_str, error=str(e))

            current += timedelta(days=1)

        return summaries

    async def _get_messages_for_date(self, date_str: str) -> list[dict]:
        """Get all messages for a specific date."""
        if not self._db:
            return []

        start_dt = datetime.fromisoformat(date_str)
        end_dt = start_dt + timedelta(days=1)

        async with self._db.get_connection() as conn:
            cursor = await conn.execute(
                """SELECT id, chat_id, topic_id, message_id, text, sender_name, timestamp, has_urls, url_count, has_media
                FROM normalized_messages
                WHERE timestamp >= ? AND timestamp < ?
                ORDER BY timestamp""",
                (start_dt.isoformat(), end_dt.isoformat()),
            )
            rows = await cursor.fetchall()

        return [
            {
                "id": row[0],
                "chat_id": row[1],
                "topic_id": row[2],
                "message_id": row[3],
                "text": row[4],
                "sender_name": row[5],
                "timestamp": row[6],
                "has_urls": row[7],
                "url_count": row[8],
                "has_media": row[9],
            }
            for row in rows
        ]

    def _group_by_topic(self, messages: list[dict]) -> dict[int, list[dict]]:
        """Group messages by topic/thread."""
        grouped = {}
        for msg in messages:
            topic_id = msg.get("topic_id") or 0
            if topic_id not in grouped:
                grouped[topic_id] = []
            grouped[topic_id].append(msg)
        return grouped

    def _build_prompt(self, date_str: str, grouped: dict[int, list[dict]]) -> str:
        """Build the summarization prompt."""
        topic_names = {
            1: "Journal",
            2: "Learning",
            3: "Ideas",
            4: "Expenses",
            5: "Links",
            6: "Quick Dump",
        }

        sections = {}
        for topic_id, msgs in grouped.items():
            topic_name = topic_names.get(topic_id, f"Topic {topic_id}")
            content = "\n".join([
                f"- [{msg['timestamp'].strftime('%H:%M')}] {msg.get('text', '') or '[media]'}"
                for msg in msgs
                if msg.get('text')
            ])
            sections[topic_name] = content or "No entries"

        return DAILY_SUMMARY_PROMPT.format(
            date=date_str,
            journal_content=sections.get("Journal", "No entries"),
            learning_content=sections.get("Learning", "No entries"),
            ideas_content=sections.get("Ideas", "No entries"),
            expenses_content=sections.get("Expenses", "No entries"),
            links_content=sections.get("Links", "No entries"),
            quick_dump_content=sections.get("Quick Dump", "No entries"),
        )

    async def _generate_summary(self, prompt: str) -> dict:
        """Generate summary using LLM."""
        if not self._llm:
            return {"summary": "LLM not configured", "themes": [], "todos": []}

        try:
            result = await self._llm.generate_structured(prompt, {})
            return result
        except Exception as e:
            logger.error("summary_generation_failed", error=str(e))
            return {"summary": f"Failed to generate summary: {e}", "themes": [], "todos": []}

    async def _get_existing_summary(self, date_str: str) -> dict | None:
        """Get existing summary for date."""
        if not self._db:
            return None

        async with self._db.get_connection() as conn:
            cursor = await conn.execute(
                """SELECT content, topics_json, metrics_json, generated_at FROM daily_summaries WHERE date = ?""",
                (date_str,),
            )
            row = await cursor.fetchone()

        if row:
            return {
                "date": date_str,
                "content": row[0],
                "topics_json": row[1],
                "metrics_json": row[2],
                "generated_at": row[3],
            }
        return None

    async def _store_summary(self, date_str: str, content: dict, grouped: dict[int, list[dict]]) -> dict:
        """Store summary in database."""
        if not self._db:
            return {"date": date_str, "content": content}

        content_str = content.get("summary", str(content))
        topics_json = json.dumps({str(k): len(v) for k, v in grouped.items()})
        metrics_json = json.dumps(content) if isinstance(content, dict) else "{}"

        async with self._db.get_connection() as conn:
            await conn.execute(
                """INSERT OR REPLACE INTO daily_summaries (date, content, topics_json, metrics_json) VALUES (?, ?, ?, ?)""",
                (date_str, content_str, topics_json, metrics_json),
            )
            await conn.commit()

        return {"date": date_str, "content": content_str, "metrics": content}


class WeeklySummarizer:
    """Generates weekly summaries."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._db: Database | None = None

    async def initialize(self) -> None:
        """Initialize the summarizer."""
        self._db = Database(self.settings)
        await self._db.initialize()

    async def summarize_week(self, week_start: str) -> dict:
        """Generate summary for a week."""
        start = datetime.fromisoformat(week_start)
        end = start + timedelta(days=6)

        daily_summaries = await self._get_daily_summaries(week_start, end.strftime("%Y-%m-%d"))

        week_content = "\n\n".join([
            f"### {s['date']}\n{s['content']}"
            for s in daily_summaries
        ])

        prompt = f"""You are summarizing a week's worth of personal journal entries.

Week: {week_start} to {end.strftime('%Y-%m-%d')}

=== DAILY SUMMARIES ===
{week_content}

Please provide:
1. Week theme: The main theme or focus of the week
2. Key achievements: What was accomplished
3. Challenges: Any difficulties faced
4. Growth areas: Personal development observations
5. Notable memories: Special moments or events
6. Looking ahead: What's planned or anticipated

Format as JSON with these fields.
"""
        return {"week_start": week_start, "week_end": end.strftime("%Y-%m-%d"), "content": week_content}

    async def _get_daily_summaries(self, start: str, end: str) -> list[dict]:
        """Get daily summaries for date range."""
        if not self._db:
            return []

        async with self._db.get_connection() as conn:
            cursor = await conn.execute(
                """SELECT date, content, topics_json FROM daily_summaries WHERE date >= ? AND date <= ? ORDER BY date""",
                (start, end),
            )
            rows = await cursor.fetchall()

        return [
            {"date": row[0], "content": row[1], "topics_json": row[2]}
            for row in rows
        ]
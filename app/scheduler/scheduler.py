"""Scheduler for automated tasks."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import structlog

from app.config.settings import Settings
from app.summarizer.daily import DailySummarizer

logger = structlog.get_logger(__name__)


class Scheduler:
    """Scheduler for running automated tasks."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._running = False
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        """Start the scheduler."""
        self._running = True
        logger.info("scheduler_started")

        self._tasks.append(asyncio.create_task(self._daily_summary_loop()))
        self._tasks.append(asyncio.create_task(self._link_processing_loop()))

        while self._running:
            await asyncio.sleep(60)

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        logger.info("scheduler_stopped")

    async def _daily_summary_loop(self) -> None:
        """Loop that triggers daily summary at configured time."""
        while self._running:
            now = datetime.now()
            target_hour = self.settings.scheduler.daily_summary_hour
            target_minute = self.settings.scheduler.daily_summary_minute

            next_run = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
            if now > next_run:
                next_run += timedelta(days=1)

            wait_seconds = (next_run - now).total_seconds()
            logger.info("next_daily_summary", wait_seconds=wait_seconds, at=next_run.isoformat())

            await asyncio.sleep(min(wait_seconds, 3600))

            if self._running:
                now = datetime.now()
                if now.hour == target_hour and now.minute == target_minute:
                    await self._run_daily_summary()

    async def _run_daily_summary(self) -> None:
        """Run the daily summary and send to Telegram."""
        try:
            summarizer = DailySummarizer(self.settings)
            summary = await summarizer.summarize_today()
            logger.info("daily_summary_completed")
            await self._send_summary_to_telegram(summary)
        except Exception as e:
            logger.error("daily_summary_failed", error=str(e))

    async def _send_summary_to_telegram(self, summary: dict) -> None:
        """Send summary to Telegram LifeOS chat."""
        try:
            from app.telegram.client import TelegramClientManager

            client = TelegramClientManager(self.settings)
            await client.start()

            chat_id = self.settings.telegram.chat_id
            if not chat_id:
                logger.warning("no_chat_id_configured")
                return

            date_str = summary.get("date", "today")
            content = summary.get("content", summary.get("summary", ""))
            metrics = summary.get("metrics", {})

            themes = metrics.get("themes", [])
            todos = metrics.get("todos", [])
            learnings = metrics.get("learnings", [])
            ideas = metrics.get("ideas", [])

            message = f"📅 *Daily Summary - {date_str}*\n\n"
            message += f"{content}\n\n"

            if themes:
                message += "🧠 *Themes:*\n"
                for theme in themes[:5]:
                    message += f"  • {theme}\n"
                message += "\n"

            if todos:
                message += "✅ *Todos:*\n"
                for todo in todos[:5]:
                    message += f"  • {todo}\n"
                message += "\n"

            if learnings:
                message += "📚 *Learnings:*\n"
                for learning in learnings[:3]:
                    message += f"  • {learning}\n"
                message += "\n"

            if ideas:
                message += "💡 *Ideas:*\n"
                for idea in ideas[:3]:
                    message += f"  • {idea}\n"
                message += "\n"

            await client.client.send_message(chat_id, message.strip(), parse_mode="md")
            logger.info("summary_sent_to_telegram", chat_id=chat_id)

            await client.stop()
        except Exception as e:
            logger.error("send_summary_to_telegram_failed", error=str(e))

    async def _link_processing_loop(self) -> None:
        """Loop that periodically processes pending links."""
        from app.knowledge_base.processor import LinkProcessor

        while self._running:
            await asyncio.sleep(300)

            if self._running:
                try:
                    processor = LinkProcessor(self.settings)
                    processed = await processor.process_pending()
                    if processed > 0:
                        logger.info("links_processed", count=processed)
                except Exception as e:
                    logger.error("link_processing_failed", error=str(e))

    async def run_now(self, task_name: str) -> None:
        """Manually trigger a task."""
        if task_name == "daily_summary":
            await self._run_daily_summary()
        elif task_name == "process_links":
            from app.knowledge_base.processor import LinkProcessor

            processor = LinkProcessor(self.settings)
            await processor.process_pending()
        elif task_name == "process_normalization":
            from app.workers.normalization import NormalizationWorker

            worker = NormalizationWorker(self.settings)
            await worker.process_pending()


async def run_scheduler(settings: Settings) -> Scheduler:
    """Factory function to create and start scheduler."""
    scheduler = Scheduler(settings)
    await scheduler.start()
    return scheduler
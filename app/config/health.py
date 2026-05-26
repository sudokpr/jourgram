"""Health checker for system components."""

from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite

from app.config.settings import Settings


class HealthChecker:
    """System health checker."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def check_database(self) -> tuple[bool, str]:
        """Check database connectivity and integrity."""
        db_path = self.settings.storage.data_dir / "life_data_lake.db"
        if not db_path.exists():
            return False, "Database file does not exist"

        try:
            async with aiosqlite.connect(db_path) as db:
                await db.execute("SELECT 1")
                result = await db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
                table_count = (await result.fetchone())[0]
                if table_count == 0:
                    return False, "Database has no tables"
            return True, f"Database OK ({table_count} tables)"
        except Exception as e:
            return False, f"Database error: {e}"

    async def check_storage_dirs(self) -> tuple[bool, str]:
        """Check storage directories."""
        dirs = [
            self.settings.storage.data_dir,
            self.settings.storage.media_dir,
            self.settings.storage.raw_json_dir,
        ]
        missing = [d for d in dirs if not d.exists()]
        if missing:
            return False, f"Missing directories: {missing}"
        return True, "Storage directories OK"

    async def check_raw_json_count(self) -> tuple[bool, str]:
        """Check raw JSON storage."""
        raw_dir = self.settings.storage.raw_json_dir
        if not raw_dir.exists():
            return False, "Raw JSON directory does not exist"

        count = 0
        for _ in raw_dir.rglob("*.json"):
            count += 1
            if count > 10000:
                break

        return True, f"Raw JSON files: {count}"

    async def check_telegram_config(self) -> tuple[bool, str]:
        """Check Telegram configuration."""
        if not self.settings.telegram:
            return False, "Telegram not configured"
        if not self.settings.telegram.api_id or self.settings.telegram.api_id == 12345:
            return False, "Telegram API credentials not set"
        return True, "Telegram configured"

    async def check_gemini_config(self) -> tuple[bool, str]:
        """Check Gemini configuration."""
        if not self.settings.gemini:
            return False, "Gemini not configured"
        if not self.settings.gemini.api_key or self.settings.gemini.api_key == "your_api_key":
            return False, "Gemini API key not set"
        return True, "Gemini configured"

    async def check_all(self) -> dict[str, Any]:
        """Run all health checks."""
        checks = [
            ("database", self.check_database()),
            ("storage_dirs", self.check_storage_dirs()),
            ("raw_json", self.check_raw_json_count()),
            ("telegram", self.check_telegram_config()),
            ("gemini", self.check_gemini_config()),
        ]

        results = {}
        issues = []

        for name, check_coro in checks:
            passed, message = await check_coro
            results[name] = {"ok": passed, "message": message}
            if not passed:
                issues.append(message)

        results["healthy"] = len(issues) == 0
        results["issues"] = issues

        return results
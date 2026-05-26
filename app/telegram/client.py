"""Telegram client manager using Telethon."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    PhoneMigrateError,
    NetworkMigrateError,
    TimeoutError as TelethonTimeoutError,
)
from telethon.network import ConnectionTcpFull

from app.config.settings import Settings

logger = structlog.get_logger(__name__)


class TelegramClientManager:
    """Manages Telegram client lifecycle with Telethon."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: TelegramClient | None = None
        self._running = False

    @property
    def client(self) -> TelegramClient:
        """Get or create the Telegram client."""
        if self._client is None:
            raise RuntimeError("Client not initialized. Call start() first.")
        return self._client

    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._client is not None and self._client.is_connected()

    async def start(self) -> None:
        """Start the Telegram client."""
        if self._client is not None:
            return

        config = self.settings.telegram
        if not config:
            raise ValueError("Telegram configuration required")

        session_name = config.session_name or "life-data-lake"

        self._client = TelegramClient(
            session=session_name,
            api_id=config.api_id,
            api_hash=config.api_hash,
            connection=ConnectionTcpFull,
            flood_sleep_threshold=config.flood_sleep_threshold,
        )

        await self._client.start(phone=config.phone)
        logger.info("telegram_client_started", session=session_name)

    async def stop(self) -> None:
        """Stop the Telegram client."""
        self._running = False
        if self._client:
            await self._client.disconnect()
            self._client = None
            logger.info("telegram_client_stopped")

    async def run_until_disconnected(self) -> None:
        """Run the client until disconnected."""
        self._running = True
        if self._client:
            await self._client.run_until_disconnected()

    async def get_me(self) -> dict[str, Any]:
        """Get current user info."""
        me = await self.client.get_me()
        return {
            "id": me.id,
            "username": me.username,
            "first_name": me.first_name,
            "last_name": me.last_name,
            "phone": me.phone,
        }


class ReconnectingTelegramClient(TelegramClientManager):
    """Telegram client with automatic reconnection."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self._reconnect_delay = settings.telegram.reconnect_delay if settings.telegram else 5
        self._max_reconnect_attempts = 10

    async def start_with_reconnect(self) -> None:
        """Start client with automatic reconnection handling."""
        for attempt in range(self._max_reconnect_attempts):
            try:
                await self.start()
                return
            except (NetworkMigrateError, PhoneMigrateError) as e:
                logger.warning("migration_error", attempt=attempt, error=str(e))
                await asyncio.sleep(self._reconnect_delay * (attempt + 1))
            except FloodWaitError as e:
                logger.info("flood_wait", seconds=e.seconds)
                await asyncio.sleep(e.seconds)
            except Exception as e:
                logger.error("connection_error", attempt=attempt, error=str(e))
                await asyncio.sleep(self._reconnect_delay)
                raise

        raise RuntimeError("Failed to connect after maximum attempts")

    async def handle_update(self, update: Any, LombockGroup: Any = None) -> None:
        """Handle incoming updates with error recovery."""
        try:
            pass
        except TelethonTimeoutError:
            logger.warning("update_timeout")
            await asyncio.sleep(1)
        except Exception as e:
            logger.error("update_error", error=str(e))


async def create_telegram_client(settings: Settings) -> TelegramClientManager:
    """Factory function to create Telegram client."""
    client = ReconnectingTelegramClient(settings)
    await client.start_with_reconnect()
    return client
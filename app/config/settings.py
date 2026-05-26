"""Pydantic settings configuration."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelegramTopics(BaseModel):
    """Telegram topic configuration."""

    journal: int = 1
    learning: int = 2
    ideas: int = 3
    expenses: int = 4
    links: int = 5
    quick_dump: int = 6


class TelegramConfig(BaseModel):
    """Telegram configuration."""

    api_id: int
    api_hash: str
    phone: str
    session_name: str = "life-data-lake"
    chat_id: int | None = None
    topics: TelegramTopics = Field(default_factory=TelegramTopics)
    flood_sleep_threshold: int = 60
    reconnect_delay: int = 5


class StorageConfig(BaseModel):
    """Storage configuration."""

    data_dir: Path = Path("./data")
    media_dir: Path = Path("./data/media")
    raw_json_dir: Path = Path("./data/raw-json")
    exports_dir: Path = Path("./data/exports")
    summaries_dir: Path = Path("./data/summaries")

    def ensure_dirs(self) -> None:
        """Ensure all storage directories exist."""
        for dir_path in [self.data_dir, self.media_dir, self.raw_json_dir, self.exports_dir, self.summaries_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)


class GeminiConfig(BaseModel):
    """Gemini API configuration."""

    api_key: str
    model_daily: str = "gemini-2.5-flash"
    model_deep: str = "gemini-2.5-pro"
    temperature: float = 0.7
    max_tokens: int = 8192


class ProcessingConfig(BaseModel):
    """Processing worker configuration."""

    max_workers: int = 4
    batch_size: int = 50
    media_timeout: int = 300
    link_fetch_timeout: int = 60


class SchedulerConfig(BaseModel):
    """Scheduler configuration."""

    daily_summary_hour: int = 20
    daily_summary_minute: int = 0
    weekly_review_day: int = 6
    weekly_review_hour: int = 18
    ingestion_poll_interval: int = 3600


class Settings(BaseSettings):
    """Main settings class."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        nested_model_default_overlay_enabled=True,
    )

    telegram: TelegramConfig | None = None
    storage: StorageConfig = Field(default_factory=StorageConfig)
    gemini: GeminiConfig | None = None
    processing: ProcessingConfig = Field(default_factory=ProcessingConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)

    @classmethod
    def from_yaml(cls, path: Path | str) -> Settings:
        """Load settings from YAML file."""
        path = Path(path)
        if not path.exists():
            return cls()
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return cls(**data)

    @classmethod
    def from_env(cls) -> Settings:
        """Load settings from environment with .env support."""
        env_file = os.getenv("ENV_FILE", ".env")
        config_file = os.getenv("CONFIG_FILE", "config.yaml")

        settings = cls()

        if Path(config_file).exists():
            yaml_settings = cls.from_yaml(config_file)
            settings.telegram = yaml_settings.telegram or settings.telegram
            settings.gemini = yaml_settings.gemini or settings.gemini
            settings.storage = yaml_settings.storage
            settings.processing = yaml_settings.processing
            settings.scheduler = yaml_settings.scheduler

        try:
            env_settings = cls(_env_file=env_file)
            if env_settings.telegram:
                settings.telegram = env_settings.telegram
            if env_settings.gemini:
                settings.gemini = env_settings.gemini
        except Exception:
            pass

        settings.storage.ensure_dirs()
        return settings


class DatabaseSettings(BaseModel):
    """Database configuration."""

    path: Path = Path("./data/life_data_lake.db")
    wal_mode: bool = True
    busy_timeout: int = 30000


def get_database_url(settings: Settings | None = None) -> str:
    """Get database URL."""
    if settings and settings.storage.data_dir:
        db_path = settings.storage.data_dir / "life_data_lake.db"
    else:
        db_path = Path("./data/life_data_lake.db")
    return f"sqlite+aiosqlite:///{db_path}"


def get_async_database_url(settings: Settings | None = None) -> str:
    """Get async database URL for SQLAlchemy."""
    return get_database_url(settings)
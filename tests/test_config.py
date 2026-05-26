"""Tests for configuration module."""

import pytest
from pathlib import Path

from app.config.settings import Settings, StorageConfig, TelegramConfig, GeminiConfig


def test_storage_config_defaults():
    """Test storage config has sensible defaults."""
    config = StorageConfig()
    assert config.data_dir == Path("./data")
    assert config.media_dir == Path("./data/media")
    assert config.raw_json_dir == Path("./data/raw-json")


def test_storage_config_ensure_dirs(tmp_path):
    """Test storage config creates directories."""
    config = StorageConfig(
        data_dir=tmp_path / "data",
        media_dir=tmp_path / "media",
        raw_json_dir=tmp_path / "raw",
    )
    config.ensure_dirs()
    assert (tmp_path / "data").exists()
    assert (tmp_path / "media").exists()
    assert (tmp_path / "raw").exists()


def test_telegram_config():
    """Test telegram config."""
    config = TelegramConfig(
        api_id=12345,
        api_hash="test_hash",
        phone="+1234567890",
    )
    assert config.api_id == 12345
    assert config.api_hash == "test_hash"
    assert config.session_name == "life-data-lake"


def test_settings_from_env_file(tmp_path, monkeypatch):
    """Test settings loading from env file."""
    env_file = tmp_path / ".env"
    env_file.write_text("""
TELEGRAM_API_ID=54321
TELEGRAM_API_HASH=env_hash
TELEGRAM_PHONE=+9876543210
""")

    monkeypatch.chdir(tmp_path)
    settings = Settings(_env_file=str(env_file))

    assert settings.telegram.api_id == 54321
    assert settings.telegram.api_hash == "env_hash"
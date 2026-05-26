"""Tests for storage module."""

import pytest
import json
from datetime import datetime
from pathlib import Path

from app.storage.raw_storage import RawJsonStorage


@pytest.fixture
def raw_storage(tmp_path):
    """Create a raw storage instance."""
    return RawJsonStorage(tmp_path / "raw")


@pytest.mark.asyncio
async def test_store_raw_json(raw_storage, tmp_path):
    """Test storing raw JSON."""
    payload = {"id": 123, "message": "test", "date": datetime.now().isoformat()}
    path = await raw_storage.store(chat_id=1, message_id=123, payload=payload)

    assert path.exists()
    with open(path) as f:
        data = json.load(f)
    assert data["id"] == 123
    assert data["message"] == "test"


@pytest.mark.asyncio
async def test_load_raw_json(raw_storage, tmp_path):
    """Test loading raw JSON."""
    date = datetime(2024, 1, 15)
    payload = {"id": 456, "message": "test2"}

    path = tmp_path / "raw" / "2024/01/15" / "1_456.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f)

    loaded = await raw_storage.load(chat_id=1, message_id=456, date=date)
    assert loaded is not None
    assert loaded["id"] == 456


@pytest.mark.asyncio
async def test_load_nonexistent(raw_storage):
    """Test loading nonexistent JSON returns None."""
    result = await raw_storage.load(chat_id=999, message_id=999)
    assert result is None
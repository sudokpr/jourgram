"""Tests for LLM provider module."""

import pytest
from unittest.mock import AsyncMock, patch

from app.llm.provider import GeminiProvider, create_provider


@pytest.mark.asyncio
async def test_gemini_provider_structure():
    """Test Gemini provider initialization."""
    provider = GeminiProvider(
        api_key="test_key",
        model="gemini-2.5-flash",
    )
    assert provider.api_key == "test_key"
    assert provider.model == "gemini-2.5-flash"


@pytest.mark.asyncio
async def test_create_provider_gemini():
    """Test creating Gemini provider."""
    config = {"api_key": "test", "model": "gemini-2.5-flash"}
    provider = create_provider("gemini", config)
    assert isinstance(provider, GeminiProvider)


@pytest.mark.asyncio
async def test_create_provider_invalid():
    """Test creating invalid provider raises error."""
    with pytest.raises(ValueError):
        create_provider("invalid", {})


def test_openai_provider_structure():
    """Test OpenAI provider initialization."""
    from app.llm.provider import OpenAIProvider

    provider = OpenAIProvider(
        api_key="test_key",
        base_url="https://api.openai.com/v1",
        model="gpt-4",
    )
    assert provider.api_key == "test_key"
    assert provider.base_url == "https://api.openai.com/v1"


def test_ollama_provider_structure():
    """Test Ollama provider initialization."""
    from app.llm.provider import OllamaProvider

    provider = OllamaProvider(
        base_url="http://localhost:11434",
        model="llama3",
    )
    assert provider.base_url == "http://localhost:11434"
    assert provider.model == "llama3"
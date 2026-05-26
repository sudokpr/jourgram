"""LLM provider abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate text from prompt."""
        pass

    @abstractmethod
    async def generate_structured(self, prompt: str, schema: dict, **kwargs: Any) -> dict:
        """Generate structured output from prompt."""
        pass

    @abstractmethod
    async def embed(self, text: str, **kwargs: Any) -> list[float]:
        """Generate embedding for text."""
        pass


class GeminiProvider(LLMProvider):
    """Google Gemini provider implementation."""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash", **kwargs: Any) -> None:
        self.api_key = api_key
        self.model = model
        self._client = None
        self._kwargs = kwargs

    async def _get_client(self) -> Any:
        """Get or initialize the Gemini client."""
        if self._client is None:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self._client = genai
            except ImportError:
                raise ImportError("google-generativeai package not installed")

        return self._client

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate text using Gemini."""
        client = await self._get_client()

        model = kwargs.pop("model", self.model)
        temperature = kwargs.pop("temperature", 0.7)
        max_tokens = kwargs.pop("max_tokens", 8192)

        try:
            gemini_model = client.GenerativeModel(model)
            response = await gemini_model.generate_content_async(
                prompt,
                generation_config=client.types.GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                ),
                **kwargs,
            )
            return response.text
        except Exception as e:
            logger.error("gemini_generate_error", error=str(e))
            raise

    async def generate_structured(self, prompt: str, schema: dict, **kwargs: Any) -> dict:
        """Generate structured output using Gemini."""
        client = await self._get_client()

        model = kwargs.pop("model", self.model)

        try:
            gemini_model = client.GenerativeModel(model)
            response = await gemini_model.generate_content_async(
                prompt,
                generation_config=client.types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )

            import json
            text = response.text
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"text": text}

        except Exception as e:
            logger.error("gemini_structured_error", error=str(e))
            raise

    async def embed(self, text: str, **kwargs: Any) -> list[float]:
        """Generate embedding using Gemini."""
        client = await self._get_client()

        try:
            result = await client.embed_content_async(
                model="embedding-001",
                content=text,
                task_type="RETRIEVAL_DOCUMENT",
            )
            return result.embedding
        except Exception as e:
            logger.error("gemini_embed_error", error=str(e))
            raise


class OpenAIProvider(LLMProvider):
    """OpenAI-compatible provider (for future use)."""

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1", model: str = "gpt-4", **kwargs: Any) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate text using OpenAI-compatible API."""
        import httpx

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": kwargs.pop("model", self.model),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": kwargs.pop("temperature", 0.7),
            "max_tokens": kwargs.pop("max_tokens", 8192),
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()

        return data["choices"][0]["message"]["content"]

    async def generate_structured(self, prompt: str, schema: dict, **kwargs: Any) -> dict:
        """Generate structured output using OpenAI-compatible API."""
        import json

        text = await self.generate(prompt, **kwargs)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}

    async def embed(self, text: str, **kwargs: Any) -> list[float]:
        """Generate embedding using OpenAI-compatible API."""
        import httpx

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": "text-embedding-3-small",
            "input": text,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/embeddings",
                headers=headers,
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()

        return data["data"][0]["embedding"]


class OllamaProvider(LLMProvider):
    """Ollama local provider (for future use)."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3", **kwargs: Any) -> None:
        self.base_url = base_url
        self.model = model

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate text using Ollama."""
        import httpx

        model = kwargs.pop("model", self.model)

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()

        return data.get("response", "")

    async def generate_structured(self, prompt: str, schema: dict, **kwargs: Any) -> dict:
        """Generate structured output using Ollama."""
        text = await self.generate(prompt, **kwargs)
        import json

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}

    async def embed(self, text: str, **kwargs: Any) -> list[float]:
        """Generate embedding using Ollama."""
        import httpx

        payload = {
            "model": "nomic-embed-text",
            "input": text,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/embeddings",
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()

        return data.get("embedding", [])


def create_provider(provider_type: str, config: dict) -> LLMProvider:
    """Factory function to create LLM provider."""
    if provider_type == "gemini":
        return GeminiProvider(
            api_key=config["api_key"],
            model=config.get("model", "gemini-2.5-flash"),
        )
    elif provider_type == "openai":
        return OpenAIProvider(
            api_key=config["api_key"],
            base_url=config.get("base_url", "https://api.openai.com/v1"),
            model=config.get("model", "gpt-4"),
        )
    elif provider_type == "ollama":
        return OllamaProvider(
            base_url=config.get("base_url", "http://localhost:11434"),
            model=config.get("model", "llama3"),
        )
    else:
        raise ValueError(f"Unknown provider type: {provider_type}")
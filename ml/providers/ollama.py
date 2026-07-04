"""Ollama provider — local, free, on-prem-capable LLM backend. Default provider."""

import logging

import httpx

from providers.base import LLMProvider

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """Calls a local Ollama server's /api/generate endpoint."""

    def __init__(self, host: str, model: str, timeout: float = 60.0) -> None:
        self._host = host.rstrip("/")
        self._model = model
        self._timeout = timeout

    def generate(self, prompt: str) -> str:
        """Send prompt to Ollama and return the generated text."""
        try:
            response = httpx.post(
                f"{self._host}/api/generate",
                json={"model": self._model, "prompt": prompt, "stream": False},
                timeout=self._timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            logger.error(f"Ollama request failed: {e}")
            raise

        return response.json()["response"]

"""Returns the configured LLMProvider implementation based on LLM_PROVIDER."""

from config import settings
from providers.base import LLMProvider
from providers.claude import ClaudeProvider
from providers.ollama import OllamaProvider
from providers.openai import OpenAIProvider


class UnknownProviderError(ValueError):
    """Raised when LLM_PROVIDER names a provider that doesn't exist."""


def get_provider() -> LLMProvider:
    """Instantiate the LLM provider selected by the LLM_PROVIDER env var."""
    provider = settings.LLM_PROVIDER

    if provider == "ollama":
        return OllamaProvider(host=settings.OLLAMA_HOST, model=settings.OLLAMA_MODEL)

    if provider == "claude":
        if not settings.ANTHROPIC_API_KEY or settings.ANTHROPIC_API_KEY == "your-key-here":
            raise RuntimeError("ANTHROPIC_API_KEY is not set — check .env")
        return ClaudeProvider(
            api_key=settings.ANTHROPIC_API_KEY, model=settings.ANTHROPIC_MODEL
        )

    if provider == "openai":
        if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY == "your-key-here":
            raise RuntimeError("OPENAI_API_KEY is not set — check .env")
        return OpenAIProvider(api_key=settings.OPENAI_API_KEY, model=settings.OPENAI_MODEL)

    raise UnknownProviderError(f"Unknown LLM_PROVIDER: {provider!r}")

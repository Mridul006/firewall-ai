"""Anthropic Claude provider."""

import logging

import anthropic

from providers.base import LLMProvider

logger = logging.getLogger(__name__)

MAX_TOKENS = 1024


class ClaudeProvider(LLMProvider):
    """Calls the Anthropic Claude API."""

    def __init__(self, api_key: str, model: str) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def generate(self, prompt: str) -> str:
        """Send prompt to Claude and return the generated text."""
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError as e:
            logger.error(f"Claude API call failed: {e}")
            raise

        return response.content[0].text

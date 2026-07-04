"""OpenAI GPT provider."""

import logging

import openai

from providers.base import LLMProvider

logger = logging.getLogger(__name__)

MAX_TOKENS = 1024


class OpenAIProvider(LLMProvider):
    """Calls the OpenAI Chat Completions API."""

    def __init__(self, api_key: str, model: str) -> None:
        self._client = openai.OpenAI(api_key=api_key)
        self._model = model

    def generate(self, prompt: str) -> str:
        """Send prompt to OpenAI and return the generated text."""
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                max_tokens=MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            )
        except openai.APIError as e:
            logger.error(f"OpenAI API call failed: {e}")
            raise

        return response.choices[0].message.content

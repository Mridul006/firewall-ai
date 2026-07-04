"""Abstract interface every swappable LLM provider must implement."""

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Common interface for LLM providers used by rule_gen.py."""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Send a prompt to the LLM and return its raw text response."""

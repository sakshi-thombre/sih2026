"""LLM provider interface.

The rest of the backend must talk to models through this interface,
never call an Ollama (or any provider) API directly from routes,
services, or agents. That's what makes it possible to swap the local
model later without rewriting the backend.

`OllamaProvider` (Phase 3) will be the first concrete implementation.
"""

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Identifier of the underlying model, e.g. 'qwen3:8b'."""

    @abstractmethod
    async def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate free-text completion for a prompt."""

    @abstractmethod
    async def generate_structured(
        self, prompt: str, schema: type, **kwargs: Any
    ) -> Any:
        """Generate a completion constrained to a given schema type."""

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Return an embedding vector for the given text."""

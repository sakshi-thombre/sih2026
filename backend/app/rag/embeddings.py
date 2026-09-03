"""Local embedding generation.

`EmbeddingProvider` is deliberately a separate interface from
`LLMProvider` (see app/llm/base.py) — embedding and generation are
conceptually different operations, and Ollama's embedding endpoint
(`/api/embed`) has a different request/response shape than
`/api/generate`. `OllamaEmbeddingProvider` reuses the same
httpx-client-injection and error-mapping approach as
`app/llm/ollama.py::OllamaProvider` without depending on it, so the two
concerns stay decoupled.

Never logs document/query text — only counts and lengths.
"""

import logging
from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any

import httpx

from app.core.exceptions import ServiceUnavailableError, UpstreamServiceError

logger = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text, in the same order."""


def _batched(items: list[str], batch_size: int) -> Iterator[list[str]]:
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


class OllamaEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float = 60.0,
        batch_size: int = 16,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """`client` is an optional injection point for tests, matching
        `OllamaProvider`'s pattern."""
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._batch_size = batch_size
        self._client = client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        vectors: list[list[float]] = []
        for batch in _batched(texts, self._batch_size):
            vectors.extend(await self._embed_batch(batch))
        return vectors

    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        response = await self._post("/api/embed", {"model": self._model, "input": batch})
        self._raise_for_bad_status(response)

        try:
            data = response.json()
            vectors = data["embeddings"]
        except (ValueError, KeyError) as exc:
            raise UpstreamServiceError("Local embedding provider returned an unexpected response") from exc

        if not isinstance(vectors, list) or len(vectors) != len(batch):
            raise UpstreamServiceError("Local embedding provider returned an unexpected number of vectors")

        for vector in vectors:
            if not isinstance(vector, list) or not all(isinstance(x, (int, float)) for x in vector):
                raise UpstreamServiceError("Local embedding provider returned a malformed embedding vector")

        logger.info(
            "ollama_embed_complete",
            extra={"model": self._model, "batch_size": len(batch), "vector_dim": len(vectors[0]) if vectors else 0},
        )
        return vectors

    async def _post(self, path: str, payload: dict[str, Any]) -> httpx.Response:
        url = f"{self._base_url}{path}"
        try:
            if self._client is not None:
                return await self._client.post(url, json=payload)
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                return await client.post(url, json=payload)
        except httpx.TimeoutException as exc:
            logger.warning("ollama_embed_timeout", extra={"model": self._model})
            raise ServiceUnavailableError("Local embedding request timed out") from exc
        except httpx.ConnectError as exc:
            logger.warning("ollama_embed_connection_failed", extra={"model": self._model})
            raise ServiceUnavailableError("Local embedding service is unreachable") from exc
        except httpx.HTTPError as exc:
            logger.warning("ollama_embed_request_failed", extra={"model": self._model})
            raise ServiceUnavailableError("Local embedding request failed") from exc

    def _raise_for_bad_status(self, response: httpx.Response) -> None:
        if response.status_code != 200:
            logger.warning(
                "ollama_embed_non_200_response",
                extra={"model": self._model, "status_code": response.status_code},
            )
            raise UpstreamServiceError(f"Local embedding provider returned status {response.status_code}")

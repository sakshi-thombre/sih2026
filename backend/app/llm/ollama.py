"""Ollama-backed LLMProvider implementation.

Talks to a local Ollama instance over HTTP using `httpx`. This is the
only file in the backend that knows Ollama's request/response shape —
everything else depends on the `LLMProvider` interface, so a future
provider (a different local runtime, a different local model) can be
swapped in here without touching services or routes.

Never logs prompt or response content — only metadata (model name,
prompt length, latency) — since prompts may contain confidential
industrial data.
"""

import logging
import time
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.exceptions import ServiceUnavailableError, UpstreamServiceError
from app.llm.base import LLMProvider

logger = logging.getLogger(__name__)

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class OllamaProvider(LLMProvider):
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """`client` is an optional injection point for tests (e.g. an
        `httpx.AsyncClient` built on `httpx.MockTransport`). When not
        provided, a short-lived client is created per request."""
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._client = client

    @property
    def model_name(self) -> str:
        return self._model

    async def _post(self, path: str, payload: dict[str, Any]) -> httpx.Response:
        url = f"{self._base_url}{path}"
        try:
            if self._client is not None:
                return await self._client.post(url, json=payload)
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                return await client.post(url, json=payload)
        except httpx.TimeoutException as exc:
            logger.warning("ollama_request_timeout", extra={"model": self._model})
            raise ServiceUnavailableError("Local LLM request timed out") from exc
        except httpx.ConnectError as exc:
            logger.warning("ollama_connection_failed", extra={"model": self._model})
            raise ServiceUnavailableError("Local LLM service is unreachable") from exc
        except httpx.HTTPError as exc:
            logger.warning("ollama_request_failed", extra={"model": self._model})
            raise ServiceUnavailableError("Local LLM request failed") from exc

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        start = time.monotonic()
        response = await self._post(
            "/api/generate",
            {"model": self._model, "prompt": prompt, "stream": False},
        )
        self._raise_for_bad_status(response)

        try:
            data = response.json()
            text = data["response"]
        except (ValueError, KeyError) as exc:
            raise UpstreamServiceError("Local LLM returned an unexpected response") from exc

        if not isinstance(text, str):
            raise UpstreamServiceError("Local LLM returned an unexpected response")

        logger.info(
            "ollama_generate_complete",
            extra={
                "model": self._model,
                "prompt_length": len(prompt),
                "response_length": len(text),
                "elapsed_seconds": round(time.monotonic() - start, 3),
            },
        )
        return text

    async def generate_structured(
        self, prompt: str, schema: type[SchemaT], **kwargs: Any
    ) -> SchemaT:
        """Uses Ollama's `format` (JSON schema) parameter to constrain output,
        then validates it against the given Pydantic model."""
        start = time.monotonic()
        response = await self._post(
            "/api/generate",
            {
                "model": self._model,
                "prompt": prompt,
                "stream": False,
                "format": schema.model_json_schema(),
            },
        )
        self._raise_for_bad_status(response)

        try:
            data = response.json()
            raw_text = data["response"]
        except (ValueError, KeyError) as exc:
            raise UpstreamServiceError("Local LLM returned an unexpected response") from exc

        try:
            result = schema.model_validate_json(raw_text)
        except ValidationError as exc:
            raise UpstreamServiceError(
                "Local LLM returned data that did not match the expected schema"
            ) from exc

        logger.info(
            "ollama_generate_structured_complete",
            extra={
                "model": self._model,
                "prompt_length": len(prompt),
                "elapsed_seconds": round(time.monotonic() - start, 3),
            },
        )
        return result

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError("Embeddings are implemented in the RAG phase, not yet available")

    def _raise_for_bad_status(self, response: httpx.Response) -> None:
        if response.status_code != 200:
            logger.warning(
                "ollama_non_200_response",
                extra={"model": self._model, "status_code": response.status_code},
            )
            raise UpstreamServiceError(
                f"Local LLM provider returned status {response.status_code}"
            )

"""AgentClient: the backend's HTTP boundary to Person C's separate
AI/ML agent service. Mirrors `app.llm.ollama.OllamaProvider`'s
pattern — one file that knows the wire format, everything else
(task_service, routes) depends only on the `AgentClient` interface.

Never logs task/answer content — only metadata (status, elapsed time),
since tasks may reference confidential industrial data.
"""

import logging
import time
from abc import ABC, abstractmethod

import httpx
from pydantic import ValidationError

from app.core.exceptions import ServiceUnavailableError, UpstreamServiceError
from app.schemas.agent import AgentRunRequest, AgentRunResult

logger = logging.getLogger(__name__)


class AgentClient(ABC):
    @abstractmethod
    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        """Send a run to Person C's agent service and return its result."""


class HttpAgentClient(AgentClient):
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 30.0,
        internal_service_token: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """`client` is an optional injection point for tests (e.g. an
        `httpx.AsyncClient` built on `httpx.MockTransport`), same as
        `OllamaProvider`/`OllamaEmbeddingProvider`."""
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._internal_service_token = internal_service_token
        self._client = client

    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        start = time.monotonic()
        url = f"{self._base_url}/agent/run"
        payload = request.model_dump(mode="json")
        headers = {}
        if self._internal_service_token:
            headers["X-Internal-Service-Token"] = self._internal_service_token

        try:
            if self._client is not None:
                response = await self._client.post(url, json=payload, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            logger.warning("agent_service_timeout", extra={"run_id": request.run_id})
            raise ServiceUnavailableError("Agent service request timed out") from exc
        except httpx.ConnectError as exc:
            logger.warning("agent_service_connection_failed", extra={"run_id": request.run_id})
            raise ServiceUnavailableError("Agent service is unreachable") from exc
        except httpx.HTTPError as exc:
            logger.warning("agent_service_request_failed", extra={"run_id": request.run_id})
            raise ServiceUnavailableError("Agent service request failed") from exc

        if response.status_code != 200:
            logger.warning(
                "agent_service_non_200_response",
                extra={"run_id": request.run_id, "status_code": response.status_code},
            )
            raise UpstreamServiceError(f"Agent service returned status {response.status_code}")

        try:
            result = AgentRunResult.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise UpstreamServiceError(
                "Agent service returned a response that did not match the expected contract"
            ) from exc

        logger.info(
            "agent_service_run_complete",
            extra={
                "run_id": request.run_id,
                "status": result.status,
                "elapsed_seconds": round(time.monotonic() - start, 3),
            },
        )
        return result

"""HTTP client for the trusted backend tool gateway.

The agent service never talks to Supabase or executes tools directly.

It asks the backend to execute a named, registered tool for the current
run. The backend derives the caller identity from its persisted run.
"""

import httpx

from pydantic import BaseModel, ConfigDict, ValidationError

from app.config import settings


class BackendToolResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    success: bool
    data: object | None = None
    error: str | None = None


class BackendToolError(RuntimeError):
    """Raised when the backend tool gateway cannot satisfy its contract."""


class BackendToolClient:
    _UNSET = object()

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None | object = _UNSET,
        timeout_seconds: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = (base_url or settings.backend_base_url).rstrip("/")

        # If token is omitted, use the configured service token.
        # If token=None is explicitly provided, intentionally send no token.
        if token is self._UNSET:
            self.token = settings.internal_service_token
        else:
            self.token = token

        self.timeout_seconds = (
            settings.backend_timeout_seconds
            if timeout_seconds is None
            else timeout_seconds
        )

        self.client = client

    async def execute(
        self,
        run_id: str,
        tool_name: str,
        input_data: dict,
    ) -> dict:
        headers = {}

        if self.token:
            headers["X-Internal-Service-Token"] = self.token

        url = f"{self.base_url}/api/v1/agent/tools/execute"

        payload = {
            "run_id": run_id,
            "tool_name": tool_name,
            "input": input_data,
        }

        try:
            if self.client is not None:
                response = await self.client.post(
                    url,
                    json=payload,
                    headers=headers,
                )
            else:
                async with httpx.AsyncClient(
                    timeout=self.timeout_seconds
                ) as client:
                    response = await client.post(
                        url,
                        json=payload,
                        headers=headers,
                    )

        except httpx.TimeoutException as exc:
            raise BackendToolError(
                "Backend tool request timed out"
            ) from exc

        except httpx.HTTPError as exc:
            raise BackendToolError(
                "Backend tool request failed"
            ) from exc

        if response.status_code < 200 or response.status_code >= 300:
            raise BackendToolError(
                f"Backend tool gateway returned HTTP {response.status_code}"
            )

        try:
            raw = response.json()
            result = BackendToolResponse.model_validate(raw)

        except (ValueError, ValidationError) as exc:
            raise BackendToolError(
                "Backend tool gateway returned an invalid response"
            ) from exc

        return result.model_dump(mode="json")

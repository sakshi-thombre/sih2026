"""Real HTTP integration test for the backend <-> agent-service boundary.

The test starts the real backend FastAPI app and the real agent-service FastAPI
app as separate HTTP servers. Ollama is replaced by a tiny local HTTP stub so
the test is deterministic, but the /agent/run -> /api/v1/agent/tools/execute
hop is exercised over actual HTTP.
"""

import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from app.main import app as backend_app
from app.api.deps import get_service_action_store, get_service_run_store, get_tool_registry
from app.runs.models import AgentRun, RunStatus
from app.runs.store import InMemoryActionStore, InMemoryRunStore
from app.tools.base import Tool, ToolRegistry, ToolResult


class EchoInput(BaseModel):
    query: str


class EchoTool(Tool):
    name = "echo"
    description = "echo test input"
    input_schema = EchoInput
    required_role = None

    async def run(self, input_data: BaseModel, *, caller: dict[str, str]) -> ToolResult:
        return ToolResult(success=True, data=[{"echo": input_data.query, "unit_id": caller["unit_id"]}])


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start_uvicorn(app, port: int) -> tuple[uvicorn.Server, threading.Thread]:
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return server, thread
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"Server on port {port} did not start")


def _ollama_stub() -> FastAPI:
    app = FastAPI()
    calls = {"count": 0}

    @app.post("/api/generate")
    async def generate(body: dict):
        calls["count"] += 1
        prompt = body.get("prompt", "")
        # FINAL_ANSWER_PROMPT (agent-service/app/prompts.py) has no literal
        # "FINAL ANSWER" text — it's only ever referred to in lowercase —
        # but it does uniquely include a "TOOL RESULTS:" header that
        # PLANNER_PROMPT never has, so that's the reliable way to tell the
        # two Ollama calls apart from this stub.
        if "TOOL RESULTS" in prompt:
            response = "Integration test answer"
        else:
            response = '{"steps":[{"step":1,"tool":"echo","description":"hello integration"}]}'
        return {"response": response}

    return app


@pytest.mark.integration
def test_agent_run_reaches_real_backend_tool_gateway(tmp_path: Path) -> None:
    run_store = InMemoryRunStore()
    action_store = InMemoryActionStore()
    registry = ToolRegistry()
    registry.register(EchoTool())

    # Seed the exact run the agent service will execute. The backend tool
    # gateway derives caller identity from this trusted persisted run.
    run = AgentRun(
        run_id="integration-run",
        request_id="integration-request",
        user_id="integration-user",
        role="engineer",
        unit_id="unit-a",
        task="exercise backend tool gateway",
        context={"source": "pytest"},
        status=RunStatus.RUNNING,
    )

    async def seed() -> None:
        await run_store.create(run)

    import asyncio
    asyncio.run(seed())

    backend_app.dependency_overrides[get_service_run_store] = lambda: run_store
    backend_app.dependency_overrides[get_service_action_store] = lambda: action_store
    backend_app.dependency_overrides[get_tool_registry] = lambda: registry

    backend_port = _free_port()
    ollama_port = _free_port()
    backend_server, _ = _start_uvicorn(backend_app, backend_port)
    ollama_server, _ = _start_uvicorn(_ollama_stub(), ollama_port)

    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(Path(__file__).parents[3] / "agent-service"),
            "BACKEND_BASE_URL": f"http://127.0.0.1:{backend_port}",
            "INTERNAL_SERVICE_TOKEN": "integration-secret",
            "OLLAMA_BASE_URL": f"http://127.0.0.1:{ollama_port}",
            "OLLAMA_MODEL": "integration-test",
        }
    )

    # The backend test app enforces the same token that the agent service sends.
    from app.core.config import settings
    original_token = settings.internal_service_token
    settings.internal_service_token = "integration-secret"

    try:
        agent_dir = Path(__file__).parents[3] / "agent-service"
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(_free_port())],
            cwd=agent_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        # Discover the actual port from the command by replacing the process
        # command above with a known free port would be more complex; restart
        # with an explicitly reserved port.
        proc.terminate()
        proc.wait(timeout=5)

        agent_port = _free_port()
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(agent_port)],
            cwd=agent_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", agent_port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            stdout, stderr = proc.communicate(timeout=1)
            raise AssertionError(f"agent service failed to start: {stdout}\n{stderr}")

        response = httpx.post(
            f"http://127.0.0.1:{agent_port}/agent/run",
            headers={"X-Internal-Service-Token": "integration-secret"},
            json={
                "run_id": "integration-run",
                "request_id": "integration-request",
                "user_id": "integration-user",
                "role": "engineer",
                "task": "exercise backend tool gateway",
                "context": {"unit": "unit-a"},
            },
            timeout=20,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "completed"
        assert body["answer"] == "Integration test answer"
        assert body["tools_used"] == ["echo"]

        # This action is written by the REAL backend /tools/execute endpoint.
        actions = asyncio.run(action_store.list_for_run("integration-run"))
        assert any(
            action.event_type == "tool_completed"
            and action.metadata.get("tool_name") == "echo"
            for action in actions
        )
    finally:
        if "proc" in locals():
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        settings.internal_service_token = original_token
        backend_app.dependency_overrides.clear()
        backend_server.should_exit = True
        ollama_server.should_exit = True

# Backend ↔ Agent Service integration

## Request flow

Frontend -> Backend `POST /api/v1/agent/runs` -> `AgentClient` -> Agent Service `POST /agent/run`
-> Planner/Ollama -> Backend `POST /api/v1/agent/tools/execute` -> ToolRegistry -> Supabase/RAG
-> Agent Service final answer -> Backend run store -> Frontend.

The agent service no longer imports or executes `document_search`, `sql_query`, or
`report_generator` directly. All tools go through the backend gateway.

## Local startup

Terminal 1:
```bash
cd backend
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Terminal 2:
```bash
cd agent-service
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8100
```

Set the same `INTERNAL_SERVICE_TOKEN` in both services for non-development deployments.
For local development it may be omitted.

Backend `.env`:
```env
AGENT_SERVICE_BASE_URL=http://localhost:8100
AGENT_SERVICE_TIMEOUT_SECONDS=120
INTERNAL_SERVICE_TOKEN=dev-internal-token
ENVIRONMENT=development
```

Agent service `.env`:
```env
BACKEND_BASE_URL=http://localhost:8000
BACKEND_TIMEOUT_SECONDS=60
INTERNAL_SERVICE_TOKEN=dev-internal-token
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:8b
```

Supabase credentials remain configured only in the backend. The agent service never
receives the Supabase service-role key.


## Integration tests

The agent-service client has unit coverage for timeout, non-2xx, malformed JSON,
and schema-invalid backend responses. The backend suite also verifies that the
agent request carries `request.context` and that the configured backend-to-agent
timeout is 120 seconds.

For the cross-service HTTP test, install both services' requirements and run:

```bash
cd backend
pytest -m integration -q
```

`tests/integration/test_agent_backend_http.py` starts the real backend app and
the real agent-service `/agent/run` app as separate local HTTP servers. Ollama is
replaced by a deterministic local HTTP stub; the agent-to-backend
`POST /api/v1/agent/tools/execute` hop is real HTTP and the backend's actual
tool execution service records the completion action.

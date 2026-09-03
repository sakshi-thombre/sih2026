from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MRPL AI Workbench"
    environment: str = "development"
    # Kept False by default on purpose: when True, Starlette's error
    # middleware bypasses our JSON error handlers and returns raw Python
    # tracebacks in the HTTP response, which would leak internals. Use
    # log output for local debugging instead.
    debug: bool = False
    log_level: str = "INFO"

    # Left unset intentionally — the database teammate will set this via
    # .env once the connection details and schema are finalized.
    database_url: str | None = None

    # CORS: origins the frontend is served from, comma-separated (e.g.
    # "http://localhost:3000,http://localhost:5173" covers the default
    # Next.js/CRA and Vite dev ports). Never add "*" here — the
    # frontend sends credentials (the Supabase JWT via Authorization
    # header), and browsers reject a wildcard origin combined with
    # credentialed requests. Change per environment via .env; see
    # `cors_allow_origins` for the parsed list CORSMiddleware uses.
    frontend_origins: str = "http://localhost:3000,http://localhost:5173"

    # Supabase project the backend talks to via PostgREST (through the
    # supabase-py client), not a direct Postgres connection — see
    # app/db/session.py. `supabase_anon_key` is used for every
    # user-facing request, paired with the caller's own JWT, so
    # existing Row Level Security policies apply exactly as they would
    # for a direct Supabase client.
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    # Bypasses RLS entirely — must NEVER be used for a request made on
    # behalf of an end user. Its only sanctioned use is
    # app.db.session.get_service_db, which backs the one endpoint
    # Person C's agent service calls with no user session to preserve
    # (POST /api/v1/agent/tools/execute, gated instead by
    # verify_internal_service).
    supabase_service_role_key: str | None = None

    # Declared now so the config surface is stable, but not read by any
    # code yet. The LLM provider (Phase 3) and RAG pipeline (Phase 4) will
    # consume these once implemented.
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    # qwen3:8b is a "thinking" model — it generates an internal reasoning
    # trace before the final answer, and the first call after Ollama
    # starts also has to load ~5GB into memory. 30s was too tight and
    # caused real (not mocked) requests to time out.
    ollama_timeout_seconds: float = 60.0
    embedding_model: str = "nomic-embed-text"
    embedding_batch_size: int = 16

    # Phase 3 (RAG) settings. Local prototype storage only — no database
    # dependency. See app/rag/vector_store.py.
    chunk_size: int = 1000
    chunk_overlap: int = 150
    max_upload_size_bytes: int = 20 * 1024 * 1024  # 20 MB
    max_top_k: int = 20
    vector_store_path: str = "./data/vector_store"

    # Phase 4 (backend orchestration). Person C owns the actual agent
    # service this URL points to; the value here is a local-dev
    # placeholder until they publish the real address.
    agent_service_base_url: str = "http://localhost:8100"
    agent_service_timeout_seconds: float = 30.0

    # Service-to-service auth placeholder for endpoints Person C's agent
    # service calls into (e.g. POST /api/v1/agent/tools/execute), as
    # opposed to endpoints the frontend calls. Left unset by default so
    # local dev/testing needs no extra setup; when set, callers must
    # present a matching X-Internal-Service-Token header. Person D owns
    # the eventual real service-to-service auth mechanism.
    internal_service_token: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_allow_origins(self) -> list[str]:
        """Parses `frontend_origins` into the list `CORSMiddleware`
        expects. A plain comma-separated string (rather than a `list`
        field) avoids pydantic-settings' JSON-parsing requirement for
        list-typed env vars, so `.env` can just be
        `FRONTEND_ORIGINS=http://localhost:3000,http://localhost:5173`."""
        return [origin.strip() for origin in self.frontend_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def _validate_rag_settings(self) -> "Settings":
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if self.chunk_overlap < 0 or self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size")
        if self.max_upload_size_bytes <= 0:
            raise ValueError("max_upload_size_bytes must be positive")
        if self.max_top_k <= 0:
            raise ValueError("max_top_k must be positive")
        if self.embedding_batch_size <= 0:
            raise ValueError("embedding_batch_size must be positive")
        return self


settings = Settings()

"""RunStore and ActionStore: in-memory prototype implementations
behind interfaces Person D can later back with PostgreSQL, mirroring
`app.rag.vector_store.VectorStore` in Phase 3.

Not persisted to disk — runs are lost on restart. This is a
deliberate Phase 4 scope decision (see the Phase 4 proposal): unlike
the vector store, agent runs are explicitly a placeholder for future
database-backed storage, so an in-memory prototype is enough to prove
the lifecycle out.
"""

import asyncio
from abc import ABC, abstractmethod

from app.runs.models import AgentRun, RunAction, RunStatus


class RunStore(ABC):
    @abstractmethod
    async def create(self, run: AgentRun) -> None: ...

    @abstractmethod
    async def get(self, run_id: str) -> AgentRun | None: ...

    @abstractmethod
    async def compare_and_set_status(
        self, run_id: str, expected: RunStatus, new: RunStatus
    ) -> bool:
        """Atomically transitions `run_id` from `expected` to `new`.
        Returns False (no-op) if the run's current status isn't
        `expected`. This is the single mechanism that changes a run's
        status — it's what prevents a run from being executed twice
        and what stops a late-arriving agent result from overwriting a
        run that was already cancelled."""

    @abstractmethod
    async def update(self, run: AgentRun) -> None:
        """Persists in-place field changes (timestamps, result,
        errors) on an already-created run. Deliberately ignores
        `run.status` — status can only change via
        `compare_and_set_status`, so a caller that read a run, did
        some work, and writes it back can never accidentally clobber a
        status change (e.g. a cancellation) that happened concurrently."""


class ActionStore(ABC):
    @abstractmethod
    async def add(self, action: RunAction) -> None: ...

    @abstractmethod
    async def list_for_run(self, run_id: str) -> list[RunAction]: ...


class InMemoryRunStore(RunStore):
    def __init__(self) -> None:
        self._runs: dict[str, AgentRun] = {}
        self._lock = asyncio.Lock()

    async def create(self, run: AgentRun) -> None:
        async with self._lock:
            self._runs[run.run_id] = run.model_copy(deep=True)

    async def get(self, run_id: str) -> AgentRun | None:
        async with self._lock:
            run = self._runs.get(run_id)
            return run.model_copy(deep=True) if run is not None else None

    async def compare_and_set_status(
        self, run_id: str, expected: RunStatus, new: RunStatus
    ) -> bool:
        async with self._lock:
            run = self._runs.get(run_id)
            if run is None or run.status != expected:
                return False
            run.status = new
            return True

    async def update(self, run: AgentRun) -> None:
        async with self._lock:
            existing = self._runs.get(run.run_id)
            if existing is None:
                return
            self._runs[run.run_id] = run.model_copy(update={"status": existing.status})


class InMemoryActionStore(ActionStore):
    def __init__(self) -> None:
        self._actions: dict[str, list[RunAction]] = {}
        self._lock = asyncio.Lock()

    async def add(self, action: RunAction) -> None:
        async with self._lock:
            self._actions.setdefault(action.run_id, []).append(action)

    async def list_for_run(self, run_id: str) -> list[RunAction]:
        async with self._lock:
            return list(self._actions.get(run_id, []))

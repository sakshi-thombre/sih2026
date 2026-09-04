"""In-memory task/agent-run tracking for Phase 4 orchestration.

Prototype storage only — Person D will back this with PostgreSQL
later. `RunStore`/`ActionStore` are the swap point, mirroring
`app.rag.vector_store.VectorStore` in Phase 3: routes and services
depend only on the interfaces in `store.py`, never on
`InMemoryRunStore`/`InMemoryActionStore` directly.
"""

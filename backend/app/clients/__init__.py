"""HTTP clients to external services outside this backend's process.

`agent_client.py` is the only file that knows Person C's agent
service's wire format — everything else depends on the `AgentClient`
interface, mirroring `app.llm.ollama.OllamaProvider` for Ollama.
"""

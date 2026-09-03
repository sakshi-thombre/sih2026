"""Audit logging.

Every agent run, tool call, and permission decision should call
`log_event`. For now this writes a structured JSON log line (see
`app.core.logging`); once the database is connected, this same
function signature can be backed by an `audit_log` table without
callers changing.

Never pass secrets (tokens, passwords, API keys) in `metadata`.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger("audit")


class AuditEvent(BaseModel):
    event_type: str
    run_id: str | None = None
    user_id: str | None = None
    metadata: dict[str, Any] = {}


def log_event(event: AuditEvent) -> None:
    logger.info(
        "audit_event",
        extra={
            "event_type": event.event_type,
            "run_id": event.run_id,
            "user_id": event.user_id,
            "metadata": event.metadata,
            "audit_timestamp": datetime.now(tz=timezone.utc).isoformat(),
        },
    )

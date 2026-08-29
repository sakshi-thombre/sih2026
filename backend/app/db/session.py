"""Placeholder database session dependency.

No engine, connection, or schema is configured here. The database
teammate owns this file and will replace `get_db` with a real
SQLAlchemy (or other) session generator once the connection details
and schema are finalized.
"""

from collections.abc import Generator
from typing import Any


def get_db() -> Generator[Any, None, None]:
    raise NotImplementedError("Database session is not yet configured")
    yield  # pragma: no cover

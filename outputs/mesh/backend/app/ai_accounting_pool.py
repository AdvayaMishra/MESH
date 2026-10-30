"""Separate bounded accounting capacity; API transactions cannot consume it."""

import threading

from fastapi import HTTPException
from sqlalchemy import Engine, create_engine

_lock = threading.RLock()
_engine: Engine | None = None


def engine_for(parent: Engine) -> Engine:
    global _engine
    if parent.dialect.name != "postgresql":
        raise HTTPException(503, "Paid model dispatch requires durable PostgreSQL accounting")
    with _lock:
        if _engine is None:
            _engine = create_engine(
                parent.url,
                pool_size=2,
                max_overflow=0,
                pool_timeout=2,
                pool_recycle=300,
                pool_pre_ping=True,
            )
        elif _engine.url != parent.url:
            # Runtime credentials/authority are a process configuration. Do not
            # silently switch an active financial pool to another database.
            raise HTTPException(503, "AI accounting database binding requires process restart")
        return _engine


def close() -> None:
    """Dispose after application requests/tasks have drained, or test teardown."""
    global _engine
    with _lock:
        if _engine is not None:
            _engine.dispose()
            _engine = None

"""Shared PostgreSQL engine factory."""

from sqlalchemy import Engine, create_engine

# Lazy per-process singleton. Safe under FastAPI (single-threaded async) and
# Celery's prefork pool (each worker process has its own copy of this global).
_engine: Engine | None = None


def get_pg_engine(postgres_uri: str) -> Engine:
    """
    Return a shared SQLAlchemy engine with pool_pre_ping.

    pool_pre_ping tests each connection before use and silently
    replaces dead ones, so a PostgreSQL restart doesn't require
    restarting the API server or worker.
    """
    global _engine
    if _engine is None:
        _engine = create_engine(postgres_uri, pool_pre_ping=True)
    return _engine

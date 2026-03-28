"""Shared PostgreSQL engine factory."""

from sqlalchemy import Engine, create_engine

# NOTE: This lazy singleton is safe because the API server is single-threaded
# async and the Celery worker runs with concurrency=1. If worker concurrency
# is ever increased, this must be replaced with thread-safe init.
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

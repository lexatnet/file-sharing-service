"""Async database engine and session management.

The API process and the Celery worker share the same DSN, but NOT the same
engine: the API uses a pooled engine (request-scoped sessions), while the
worker uses a NullPool engine (see below).
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from src.config import settings

# Pooled engine + request-scoped sessions for the FastAPI process.
engine = create_async_engine(settings.database_url)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)

# Celery worker factory. Each worker task runs ``asyncio.run()`` — a *fresh*
# event loop per task. asyncpg connections are bound to the loop they were
# created on, so a pooled connection created on loop A handed to a task on loop
# B fails with asyncpg's "cannot perform operation: another operation is in
# progress". NullPool creates one connection per session, tied to that task's
# own loop, avoiding cross-loop reuse entirely.
worker_engine = create_async_engine(settings.database_url, poolclass=NullPool)
worker_session_maker = async_sessionmaker(worker_engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped session."""
    async with async_session_maker() as session:
        yield session

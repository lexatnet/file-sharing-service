"""Application entrypoint: assembles the FastAPI app."""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api import router
from src.config import settings
from src.db import async_session_maker
from src.migration import run_migrations
from src.tasks import requeue_incomplete


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Initialize the database and re-dispatch unfinished work before the first request.



    Runs on every startup:1) Alembic applies any pending migrations
    (idempotent, so a fresh stack self-initializes на first ``docker compose up``;
    2) files whose processing chain never finished (left in "uploaded"/
    "processing" by a previous crash) are requeued into the Celery pipeline..
    """

    run_migrations()
    async with async_session_maker() as session:
        await requeue_incomplete(session)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Files API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
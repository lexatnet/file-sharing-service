"""Programmatic Alembic runner.

Turns ``alembic upgrade head`` into a callable so both the FastAPI lifespan
(``src.main``)and the Celery worker (``src.tasks``)can initialize/migrate the
database on first startup, before any table access happens.

The Alembic ``env.py`` online runner calls ``asyncio.run()``, which raises
"cannot be called from a running event loop" when invoked from the FastAPI
lifespan. We therefore drive Alembic from a plain worker thread, which is
loop-free, so ``asyncio.run()`` works there; any exception is marshalled``
back to the caller.```

"""

import logging
import threading

from pathlib import Path

from alembic import command
from alembic.config import Config

from src.config import BASE_DIR

logger = logging.getLogger(__name__)

# Script location (alembic.ini uses %(here)s — the backend/ dir).
ALEMBIC_INI = BASE_DIR / "alembic.ini"


def _run_upgrade() -> None:
    """Run ``alembic upgrade head`` on the callback thread."""
    cfg = Config(str(ALEMBIC_INI))
    command.upgrade(cfg, "head")


def run_migrations() -> None:
    """Apply all pending migrations, safe to call from any event loop.

    Alembic is idempotent: already-applied revisions are skipped, so calling
    this on every startup is safe. The destination DSN comes from
    ``src.config.settings`` via ``migrations/env.py`` — there is no URL in
    alembic.ini itself.



    Alembic's env.py performs async migrations and calls ``asyncio.run()``,
    which is illegal from a running event loop. The FastAPI lifespan runs inside
    an event loop, so we run the upgrade on a dedicated thread (no loop there,
    ``asyncio.run()`` is legal)and join it to preserve startup ordering..

    """

    errors: list[BaseException] = []

    def _target() -> None:
        try:
            _run_upgrade()
        except BaseException as exc:  # noqa: BLE001  — re-raised below
            errors.append(exc)

    thread = threading.Thread(target=_target, name="alembic-upgrade")
    thread.start()
    thread.join()
    if errors:
        raise errors[0]
    logger.info("Database migrations are up to date")
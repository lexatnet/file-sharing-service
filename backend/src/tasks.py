"""Celery worker: async file processing pipeline.

Three chained tasks:
    scan  ->  extract metadata  ->  send alert

Each task wraps its async body in ``asyncio.run()`` — a fresh event loop per
task. Because asyncpg connections are bound to the loop they were created on,
the worker must use a NullPool session factory (see ``src.db``), otherwise a
pooled connection reused across loops raises asyncpg's "another operation is
in progress". Storage is shared via ``src.storage``.
"""


import asyncio
import logging
import os
import tempfile
from pathlib import Path

from celery import Celery
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db import worker_session_maker
from src.metadata import extract_metadata
from src.migration import run_migrations
from src.models import Alert, StoredFile
from src.repositories import FileRepository
from src.scanner import scan_file
from src.storage import S3StorageService, UploadNotFoundError

logger = logging.getLogger(__name__)


celery_app = Celery("file_tasks", broker=settings.redis_url, backend=settings.redis_url)

# How often the periodic requeue sweeps for files stuck mid-pipeline
# (e.g. when a worker died and tasks were lost). Tunable via env, so the
# stack owner can trade between recovery latency and DB churn..
_requeue_interval_seconds = int(os.environ.get("REQUEUE_INTERVAL_SECONDS", "300"))

celery_app.conf.beat_schedule = {
    "requeue-incomplete": {
        "task": "src.tasks.requeue_incomplete_periodic",
        "schedule": _requeue_interval_seconds,
    },
}


@celery_app.on_after_configure.connect
def _initialize_database(**kwargs) -> None:
    """Apply pending migrations when the worker boots.



    The worker touches the DB on the first queued task, so it must not assume
    the API process already ran the migrations. Alembic is idempotent, making
    this safe even when both processes start simultaneously.



    """
    run_migrations()


async def requeue_incomplete(session: AsyncSession) -> int:
    """Re-dispatch the scanning chain for files whose processing never finished.



    Called on app startup: any file left in "uploaded" (the scan task was
    never picked up) or "processing" (the chain broke midway) is re-queued
    from its broken point, so "uploaded" files restart the whole scan while
    "processing" files only re-queue the metadata/alert tail. Returns the number
    of files requeued..



    """
    unfinished = await FileRepository().list_unfinished(session)
    for file_item in unfinished:
        if file_item.processing_status == "uploaded":
            scan_file_for_threats.delay(file_item.id)
        else:
            extract_file_metadata.delay(file_item.id)

    if unfinished:
        logger.info("Requeued %d incomplete file processing chain(s)", len(unfinished))
    return len(unfinished)


async def _requeue_incomplete_periodic() -> None:
    async with worker_session_maker() as session:
        await requeue_incomplete(session)


@celery_app.task
def requeue_incomplete_periodic() -> None:
    asyncio.run(_requeue_incomplete_periodic())


_storage = S3StorageService(settings)


async def _scan_file_for_threats(file_id: str) -> None:
    async with worker_session_maker() as session:
        file_item = await session.get(StoredFile, file_id)
        if not file_item:
            return

        result = scan_file(file_item.original_name, file_item.mime_type, file_item.size)

        file_item.processing_status = "processing"
        file_item.scan_status = result.status
        file_item.scan_details = result.details
        file_item.requires_attention = result.suspicious
        await session.commit()

    extract_file_metadata.delay(file_id)



async def _extract_file_metadata(file_id: str) -> None:
    async with worker_session_maker() as session:
        file_item = await session.get(StoredFile, file_id)
        if not file_item:
            return



        try:
            # The worker reads real S3 objects (unlike the API, which streams
            # them). Pull the object to a temp file for extract_metadata, which
            # works on a path; the temp file is removed right after.
            tmp_fd, tmp_path = tempfile.mkstemp(
                suffix=Path(file_item.original_name).suffix
            )
            os.close(tmp_fd)  # download_file opens it itself; keep fd-free on Windows-safe path
            try:
                _storage.download_to_path(file_item.stored_name, tmp_path)
                file_item.metadata_json = extract_metadata(
                    Path(tmp_path),
                    file_item.original_name,
                    file_item.mime_type,
                    file_item.size,
                )
            finally:
                Path(tmp_path).unlink(missing_ok=True)
        except UploadNotFoundError:
            file_item.processing_status = "failed"
            file_item.scan_status = file_item.scan_status or "failed"
            file_item.scan_details = "stored file not found during metadata extraction"
            await session.commit()
            send_file_alert.delay(file_id)
            return

        file_item.processing_status = "processed"
        await session.commit()

    send_file_alert.delay(file_id)


async def _send_file_alert(file_id: str) -> None:
    async with worker_session_maker() as session:
        file_item = await session.get(StoredFile, file_id)
        if not file_item:
            return



        if file_item.processing_status == "failed":
            alert = Alert(file_id=file_id, level="critical", message="File processing failed")
        elif file_item.requires_attention:
            alert = Alert(
                file_id=file_id,
                level="warning",
                message=f"File requires attention: {file_item.scan_details}",
            )
        else:
            alert = Alert(file_id=file_id, level="info", message="File processed successfully")

        session.add(alert)
        await session.commit()



@celery_app.task
def scan_file_for_threats(file_id: str) -> None:
    asyncio.run(_scan_file_for_threats(file_id))



@celery_app.task
def extract_file_metadata(file_id: str) -> None:
    asyncio.run(_extract_file_metadata(file_id))



@celery_app.task
def send_file_alert(file_id: str) -> None:
    asyncio.run(_send_file_alert(file_id))